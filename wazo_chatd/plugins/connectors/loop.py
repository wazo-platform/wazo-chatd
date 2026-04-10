# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import itertools
import logging
import threading
import time
from collections.abc import Coroutine
from types import TracebackType
from typing import Any

import asyncpg
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from wazo_chatd.bus import BusPublisher
from wazo_chatd.database.async_helpers import (
    async_session_scope,
    init_async_db,
    parse_ssl_from_uri,
)
from wazo_chatd.database.queries.async_.user_identity import AsyncUserIdentityDAO
from wazo_chatd.plugin_helpers.dependencies import ConfigDict
from wazo_chatd.plugins.connectors.executor import DeliveryExecutor
from wazo_chatd.plugins.connectors.notifier import AsyncNotifier
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.store import ConnectorStore
from wazo_chatd.plugins.connectors.types import InboundMessage, StatusUpdate

logger = logging.getLogger(__name__)


def _backoff() -> itertools.chain[int]:
    return itertools.chain([1, 2, 4, 8, 16, 32], itertools.repeat(32))


class DeliveryLoop:
    def __init__(
        self,
        config: ConfigDict,
        registry: ConnectorRegistry,
        store: ConnectorStore,
    ) -> None:
        self._config = config
        self._registry = registry
        self._store = store
        self._max_tasks = int(config['delivery']['max_concurrent_tasks'])

        self._db_uri = str(config.get('db_uri', ''))
        engine, session_factory = init_async_db(self._db_uri)
        self._engine = engine
        self._session_factory = session_factory

        bus_publisher = BusPublisher.from_config(
            service_uuid=config.get('uuid', ''),
            bus_config=config.get('bus', {}),
        )
        self._executor = DeliveryExecutor(
            config=config,
            registry=registry,
            notifier=AsyncNotifier(bus_publisher),
            store=store,
        )

        self._backoff = _backoff()
        self._healthy: bool = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._shutdown: asyncio.Future[None] | None = None
        self._thread: threading.Thread | None = None
        self._in_flight: set[asyncio.Task[None]] = set()
        self._semaphore: asyncio.Semaphore | None = None
        self._listener_task: asyncio.Task[None] | None = None
        self._restart_count: int = 0

    def _init_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._semaphore = asyncio.Semaphore(self._max_tasks)
        self._shutdown = self._loop.create_future()

    def __enter__(self) -> DeliveryLoop:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.shutdown()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            raise RuntimeError('DeliveryLoop has not been started')
        return self._loop

    @property
    def semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            raise RuntimeError('DeliveryLoop has not been started')
        return self._semaphore

    def start(self) -> None:
        logger.info('Starting delivery loop')
        self._init_loop()

        self._thread = threading.Thread(
            target=self._run_loop,
            name='delivery-loop',
            daemon=True,
        )
        self._thread.start()
        logger.info('Delivery loop started')

    def shutdown(self, timeout: float = 10) -> None:
        logger.info('Stopping delivery loop')

        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self._drain_and_stop(), self._loop
            )
            future.result(timeout=timeout)

        if self._thread:
            self._thread.join(timeout=timeout)

        logger.info('Delivery loop stopped')

    def enqueue_message(
        self,
        message: InboundMessage | StatusUpdate,
        delay: float | None = None,
    ) -> None:
        if delay:
            self.loop.call_soon_threadsafe(
                self.loop.call_later, delay, self._schedule_task, message
            )
        else:
            self.loop.call_soon_threadsafe(self._schedule_task, message)

    @property
    def is_running(self) -> bool:
        loop_running = self._loop is not None and self._loop.is_running()
        thread_running = self._thread is not None and self._thread.is_alive()
        return loop_running and thread_running

    @property
    def in_flight_count(self) -> int:
        return len(self._in_flight)

    @property
    def restart_count(self) -> int:
        return self._restart_count

    def _run_loop(self) -> None:
        loop = self._loop
        assert loop is not None

        asyncio.set_event_loop(loop)
        loop.create_task(self._startup())
        try:
            loop.run_forever()
        except Exception:
            logger.exception('Delivery loop crashed, restarting')
            self._teardown_loop(loop)
            self._restart()
            return

        self._teardown_loop(loop)

    async def _startup(self) -> None:
        await self._populate_store()
        await self._recover()
        self._listener_task = asyncio.ensure_future(self._listen_for_deliveries())

    async def _populate_store(self) -> None:
        try:
            async with async_session_scope(self._session_factory):
                dao = AsyncUserIdentityDAO()
                tenant_backends = await dao.list_tenant_backends()
        except Exception:
            logger.exception('Failed to scan tenant backends for store population')
            return

        sem = asyncio.Semaphore(20)

        async def _load(backend: str, tenant_uuid: str) -> None:
            async with sem:
                await self._store.refresh(backend, tenant_uuid)

        await asyncio.gather(
            *(_load(backend, tenant_uuid) for tenant_uuid, backend in tenant_backends)
        )

        logger.info('Populated connector store with %d instance(s)', len(self._store))

    def _teardown_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._in_flight:
            logger.warning('%d in-flight task(s) dropped', len(self._in_flight))
            self._in_flight.clear()

        if not loop.is_closed():
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    def _restart(self) -> None:
        if self._healthy:
            self._backoff = _backoff()
            self._healthy = False

        delay = next(self._backoff)
        self._restart_count += 1
        logger.warning(
            'Restarting delivery loop in %ds (attempt #%d)',
            delay,
            self._restart_count,
        )
        time.sleep(delay)

        self._init_loop()
        self._run_loop()

    async def _listen_for_deliveries(self) -> None:
        assert self._shutdown is not None
        ssl = parse_ssl_from_uri(self._db_uri)
        backoff = _backoff()

        while not self._shutdown.done():
            connection: asyncpg.Connection | None = None
            try:
                connection = await asyncpg.connect(self._db_uri, ssl=ssl)
                await connection.add_listener(
                    'connector_delivery', self._on_delivery_notify
                )
                logger.info('Listening for connector_delivery notifications')
                backoff = _backoff()

                await self._shutdown
            except asyncio.CancelledError:
                break
            except Exception:
                delay = next(backoff)
                logger.exception('Listener connection lost, reconnecting in %ds', delay)
                await asyncio.sleep(delay)
            finally:
                if connection and not connection.is_closed():
                    await connection.close()

        logger.info('Stopped listening for connector_delivery notifications')

    def _on_delivery_notify(
        self,
        connection: asyncpg.Connection,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        message_uuid = payload
        logger.debug('Received delivery notification for message %s', message_uuid)
        self._schedule_outbound_notification(message_uuid)

    def _schedule_outbound_notification(self, message_uuid: str) -> None:
        assert self._loop is not None
        task = self._loop.create_task(self._process_outbound_notification(message_uuid))
        self._in_flight.add(task)
        task.add_done_callback(self._task_done)

    async def _process_outbound_notification(self, message_uuid: str) -> None:
        async with self.semaphore:
            try:
                async with async_session_scope(self._session_factory):
                    meta = await self._executor._room_dao.get_message_meta(message_uuid)
                    if not meta:
                        logger.error(
                            'No MessageMeta found for notified message %s',
                            message_uuid,
                        )
                        return

                    if not meta.message or not meta.message.room:
                        logger.warning(
                            'Message %s or its room was deleted before delivery',
                            message_uuid,
                        )
                        return

                    await self._executor.route_outbound(meta)
            except (StaleDataError, IntegrityError):
                logger.warning(
                    'Message %s was deleted during delivery, skipping',
                    message_uuid,
                )
            except Exception:
                logger.exception(
                    'Failed to process delivery notification for %s', message_uuid
                )

    async def _recover(self) -> None:
        try:
            async with async_session_scope(self._session_factory):
                recoverable = await self._executor.recover_pending_deliveries()
        except Exception:
            logger.exception('Recovery scan failed, continuing without recovery')
            return

        assert self._loop is not None
        for meta, delay in recoverable:
            message_uuid = str(meta.message_uuid)

            if delay > 0:
                logger.info(
                    'Recovery: re-enqueuing %s with %.0fs delay',
                    message_uuid,
                    delay,
                )
                self._loop.call_later(
                    delay, self._schedule_outbound_notification, message_uuid
                )
            else:
                logger.info('Recovery: re-enqueuing %s immediately', message_uuid)
                self._schedule_outbound_notification(message_uuid)

    def _schedule_task(self, message: InboundMessage | StatusUpdate) -> None:
        assert self._loop is not None

        match message:
            case InboundMessage():
                coro = self._executor.route_inbound(message)
            case StatusUpdate():
                coro = self._executor.route_status_update(message)
            case _:
                return

        task = self._loop.create_task(self._process(coro, message))
        self._in_flight.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task[None]) -> None:
        self._in_flight.discard(task)
        if task.exception() is None:
            self._healthy = True

    async def _process(
        self,
        coro: Coroutine[Any, Any, None],
        message: InboundMessage | StatusUpdate,
    ) -> None:
        async with self.semaphore:
            logger.debug('Processing %s', message)
            try:
                async with async_session_scope(self._session_factory):
                    await coro
            except Exception:
                logger.exception('Failed to process %s', message)

    async def _drain_and_stop(self) -> None:
        if self._shutdown and not self._shutdown.done():
            self._shutdown.set_result(None)

        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._in_flight:
            logger.info(
                'Waiting for %d in-flight task(s) to complete',
                len(self._in_flight),
            )
            await asyncio.gather(*self._in_flight, return_exceptions=True)

        if self._engine:
            await self._engine.dispose()
            logger.debug('Async database engine disposed')

        assert self._loop is not None
        self._loop.stop()
