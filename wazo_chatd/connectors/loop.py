# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import logging
import threading
import time
from types import TracebackType

from wazo_chatd.bus import BusPublisher
from wazo_chatd.connectors.executor import DeliveryExecutor
from wazo_chatd.connectors.store import ConnectorStore
from wazo_chatd.connectors.notifier import AsyncNotifier
from wazo_chatd.connectors.registry import ConnectorRegistry
from wazo_chatd.connectors.types import InboundMessage, OutboundMessage, StatusUpdate
from wazo_chatd.database.async_helpers import async_session_scope, init_async_db

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CONCURRENT_TASKS = 100
_RESTART_BACKOFF_MAX = 32


class DeliveryLoop:
    def __init__(
        self,
        config: dict[str, str | bool],
        registry: ConnectorRegistry,
        store: ConnectorStore,
    ) -> None:
        self._config = config
        self._registry = registry
        self._store = store
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._executor: DeliveryExecutor | None = None
        self._max_tasks = int(
            config.get('max_concurrent_tasks', _DEFAULT_MAX_CONCURRENT_TASKS)
        )
        self._in_flight: set[asyncio.Task[None]] = set()
        self._semaphore: asyncio.Semaphore | None = None
        self._restart_count: int = 0

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

    def initialize(self) -> None:
        engine, session_factory = init_async_db(str(self._config.get('db_uri', '')))
        self._engine = engine
        self._session_factory = session_factory

        bus_publisher = BusPublisher.from_config(
            service_uuid=self._config.get('uuid', ''),
            bus_config=self._config.get('bus', {}),
        )
        notifier = AsyncNotifier(bus_publisher)

        self._executor = DeliveryExecutor(
            config=self._config,
            registry=self._registry,
            notifier=notifier,
            store=self._store,
        )

    def start(self) -> None:
        logger.info('Starting delivery loop')
        self.initialize()

        self._loop = asyncio.new_event_loop()
        self._semaphore = asyncio.Semaphore(self._max_tasks)

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
        message: OutboundMessage | InboundMessage | StatusUpdate,
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
        asyncio.set_event_loop(self._loop)
        assert self._loop is not None

        try:
            self._loop.run_forever()
        except Exception:
            logger.exception('Delivery loop crashed, restarting')
            self._restart()
        finally:
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.close()

    def _restart(self) -> None:
        if (old_loop := self._loop) and not old_loop.is_closed():
            old_loop.run_until_complete(old_loop.shutdown_asyncgens())
            old_loop.close()

        delay = min(2**self._restart_count, _RESTART_BACKOFF_MAX)
        self._restart_count += 1
        logger.warning(
            'Restarting delivery loop in %ds (attempt #%d)',
            delay,
            self._restart_count,
        )
        time.sleep(delay)

        self._in_flight.clear()
        self._loop = asyncio.new_event_loop()
        self._semaphore = asyncio.Semaphore(self._max_tasks)
        self._run_loop()

    def _schedule_task(
        self, message: OutboundMessage | InboundMessage | StatusUpdate
    ) -> None:
        assert self._loop is not None

        match message:
            case OutboundMessage():
                task = self._loop.create_task(self._process_outbound(message))
            case InboundMessage():
                task = self._loop.create_task(self._process_inbound(message))
            case StatusUpdate():
                task = self._loop.create_task(self._process_status_update(message))
            case _:
                return
        self._in_flight.add(task)
        task.add_done_callback(self._in_flight.discard)

    async def _process_outbound(self, message: OutboundMessage) -> None:
        assert self._semaphore is not None
        assert self._executor is not None

        async with self._semaphore:
            logger.debug(
                'Processing outbound message (message=%s)',
                message.message_uuid,
            )
            try:
                async with async_session_scope(self._session_factory):
                    await self._executor.route_outbound(message)
                logger.debug(
                    'Outbound message processed (message=%s)',
                    message.message_uuid,
                )
            except Exception:
                logger.exception(
                    'Failed to process outbound message %s', message.message_uuid
                )

    async def _process_inbound(self, message: InboundMessage) -> None:
        assert self._semaphore is not None
        assert self._executor is not None

        async with self._semaphore:
            logger.debug(
                'Processing inbound message (backend=%s)',
                message.backend,
            )
            try:
                async with async_session_scope(self._session_factory):
                    await self._executor.route_inbound(message)
            except Exception:
                logger.exception(
                    'Failed to process inbound message (external_id=%s)',
                    message.external_id,
                )

    async def _process_status_update(self, update: StatusUpdate) -> None:
        assert self._semaphore is not None
        assert self._executor is not None

        async with self._semaphore:
            logger.debug(
                'Processing status update (external_id=%s, status=%s)',
                update.external_id,
                update.status,
            )
            try:
                async with async_session_scope(self._session_factory):
                    await self._executor.route_status_update(update)
            except Exception:
                logger.exception(
                    'Failed to process status update (external_id=%s)',
                    update.external_id,
                )

    async def _drain_and_stop(self) -> None:
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
