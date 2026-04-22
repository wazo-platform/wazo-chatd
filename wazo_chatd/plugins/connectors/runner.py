# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import inspect
import itertools
import logging
import threading
from collections.abc import Callable, Coroutine
from types import TracebackType
from typing import Any, ClassVar

import asyncpg
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from wazo_chatd.bus import BusPublisher
from wazo_chatd.database.async_helpers import (
    async_session_scope,
    build_asyncpg_connect_args,
    init_async_db,
)
from wazo_chatd.plugin_helpers.dependencies import ConfigDict
from wazo_chatd.plugin_helpers.queue import AsyncQueue, QueueFull
from wazo_chatd.plugins.connectors.connector import Connector
from wazo_chatd.plugins.connectors.executor import DeliveryExecutor
from wazo_chatd.plugins.connectors.notifier import AsyncNotifier
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.store import CacheKey, ConnectorStore
from wazo_chatd.plugins.connectors.types import InboundMessage, StatusUpdate

logger = logging.getLogger(__name__)


def _backoff() -> itertools.chain[int]:
    return itertools.chain([1, 2, 4, 8, 16, 32], itertools.repeat(32))


class Runner:
    """Event loop running on a dedicated daemon thread.

    Handles thread + loop lifecycle (via :func:`asyncio.run`), crash
    recovery with iterative exponential backoff, and a
    loop-independent close signal that survives restarts.

    :meth:`run` is the thread target. :meth:`start` spawns that
    thread; :meth:`shutdown` signals ``_closing`` and joins.

    Subclasses override :meth:`_on_start` (setup coroutine) and
    :meth:`_on_stop` (async cleanup). Both run inside the loop. The
    base guarantees ``_on_stop`` runs even if ``_on_start`` raises.
    Rare cases that need interleaved setup/steady/teardown may
    override :meth:`_entrypoint` directly.
    """

    thread_name: ClassVar[str] = 'runner'
    shutdown_timeout: ClassVar[float] = 10.0

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = threading.Thread(
            target=self.run, name=self.thread_name, daemon=True
        )
        self._ready = threading.Event()
        # Loop-independent, created once, survives restarts.
        # Set from any thread via shutdown(); observed from async via
        # _wait_closing() or is_closing.
        self._closing: concurrent.futures.Future[None] = concurrent.futures.Future()
        self._backoff = _backoff()
        self._restart_count: int = 0
        self._healthy: threading.Event = threading.Event()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            raise RuntimeError(f'{type(self).__name__} has not been started')
        return self._loop

    @property
    def is_running(self) -> bool:
        return self._loop is not None and self._loop.is_running()

    @property
    def is_closing(self) -> bool:
        return self._closing.done()

    @property
    def restart_count(self) -> int:
        return self._restart_count

    def run(self) -> None:
        """Thread target: run the async lifecycle, restart on crash."""
        while True:
            try:
                asyncio.run(self._entrypoint())
                return
            except Exception:
                logger.exception('%s crashed, restarting', self.thread_name)
            finally:
                self._loop = None

            if not self._wait_backoff():
                return

    async def _entrypoint(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._ready.set()
        start_task: asyncio.Task[None] = asyncio.create_task(self._on_start())
        close_future = asyncio.wrap_future(self._closing)
        try:
            done, pending = await asyncio.wait(
                [start_task, close_future],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if start_task in pending:
                # Shutdown signaled during _on_start — abort setup.
                start_task.cancel()
                try:
                    await start_task
                except (asyncio.CancelledError, Exception):
                    pass
            else:
                # _on_start completed — re-raise if it crashed, so
                # run() can log and trigger the restart path.
                start_task.result()
                await close_future
        finally:
            await self._on_stop()

    def start(self) -> None:
        if self._thread.is_alive() or self._thread.ident is not None:
            raise RuntimeError(f'{type(self).__name__} already started')
        logger.info('Starting %s', self.thread_name)
        self._thread.start()
        self._ready.wait(timeout=self.shutdown_timeout)
        logger.info('Started %s', self.thread_name)

    def shutdown(self) -> None:
        logger.info('Stopping %s', self.thread_name)
        if not self._closing.done():
            self._closing.set_result(None)
        self._thread.join(timeout=self.shutdown_timeout)
        logger.info('Stopped %s', self.thread_name)

    def __enter__(self) -> Runner:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.shutdown()

    def _wait_backoff(self) -> bool:
        """Sleep with exponential backoff.

        Returns ``False`` if shutdown was requested during the sleep
        (caller should exit), ``True`` otherwise (caller should
        restart).
        """
        if self._healthy.is_set():
            self._backoff = _backoff()
            self._healthy.clear()

        delay = next(self._backoff)
        self._restart_count += 1
        logger.warning(
            'Restarting %s in %ds (attempt #%d)',
            self.thread_name,
            delay,
            self._restart_count,
        )
        try:
            self._closing.result(timeout=delay)
            return False
        except concurrent.futures.TimeoutError:
            return True

    async def _wait_closing(self) -> None:
        """Subclass helper: resolve when shutdown has been requested."""
        await asyncio.wrap_future(self._closing)

    async def _on_start(self) -> None:
        """Override to schedule work when the loop starts."""

    async def _on_stop(self) -> None:
        """Override for cleanup before the loop stops."""


class DeliveryRunner(Runner):
    thread_name: ClassVar[str] = 'delivery-runner'

    def __init__(
        self,
        config: ConfigDict,
        registry: ConnectorRegistry,
        store: ConnectorStore,
    ) -> None:
        super().__init__()
        self._config = config
        self._registry = registry
        self._store = store
        self._max_tasks = int(config['delivery']['max_concurrent_tasks'])
        self._poll_min = float(config['delivery'].get('poll_interval_min', 5))
        self._poll_max = float(config['delivery'].get('poll_interval_max', 60))
        self._poll_default = float(config['delivery'].get('poll_interval_default', 30))

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

        self._in_flight: set[asyncio.Task[None]] = set()
        self._semaphore: asyncio.Semaphore | None = None
        self._outbound_notify_task: asyncio.Task[None] | None = None
        self._pollers: dict[CacheKey, asyncio.Task[None]] = {}
        self._queue: AsyncQueue[InboundMessage | StatusUpdate] = AsyncQueue()
        self._drain_task: asyncio.Task[None] | None = None
        self._scheduled_timers: set[asyncio.TimerHandle] = set()

    @property
    def semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            raise RuntimeError('DeliveryRunner has not been started')
        return self._semaphore

    @property
    def in_flight_count(self) -> int:
        return len(self._in_flight)

    def enqueue_message(self, message: InboundMessage | StatusUpdate) -> None:
        try:
            self._queue.append(message)
        except QueueFull:
            logger.warning(
                'Delivery queue full (%d), dropping %s',
                len(self._queue),
                message,
            )

    async def _on_start(self) -> None:
        self._semaphore = asyncio.Semaphore(self._max_tasks)
        try:
            await self._store.wait_populated()
        except Exception:
            logger.exception(
                '%s starting in degraded state: connector store populate failed',
                self.thread_name,
            )
        self._outbound_notify_task = asyncio.create_task(self._listen_for_deliveries())
        self._drain_task = asyncio.create_task(self._drain_queue())
        self._synchronize_pollers()

    async def _drain_queue(self) -> None:
        try:
            async for message in self._queue:
                self._schedule_task(message)
        except asyncio.CancelledError:
            raise

    async def _on_stop(self) -> None:
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass

        if self._outbound_notify_task and not self._outbound_notify_task.done():
            self._outbound_notify_task.cancel()
            try:
                await self._outbound_notify_task
            except asyncio.CancelledError:
                pass

        for task in list(self._pollers.values()):
            if not task.done():
                task.cancel()
        if self._pollers:
            await asyncio.gather(*self._pollers.values(), return_exceptions=True)
        self._pollers.clear()

        for handle in self._scheduled_timers:
            handle.cancel()
        self._scheduled_timers.clear()

        if self._in_flight:
            logger.info(
                'Waiting for %d in-flight task(s) to complete',
                len(self._in_flight),
            )
            await asyncio.gather(*self._in_flight, return_exceptions=True)
        self._in_flight.clear()

        if self.is_closing and self._engine:
            await self._engine.dispose()
            logger.debug('Async database engine disposed')

    async def _listen_for_deliveries(self) -> None:
        backoff = _backoff()

        while not self.is_closing:
            connection: asyncpg.Connection | None = None
            try:
                driver_uri, connect_args = build_asyncpg_connect_args(self._db_uri)
                connection = await asyncpg.connect(driver_uri, **connect_args)
                await connection.add_listener(
                    'connector_delivery', self._on_delivery_notify
                )
                logger.info('Listening for connector_delivery notifications')
                backoff = _backoff()

                # Run recovery after LISTEN is registered so any NOTIFY
                # fired during the outage (or startup) is picked up
                # either by the live listener or this catch-up scan.
                await self._recover()

                await self._wait_closing()
            except asyncio.CancelledError:
                break
            except Exception:
                delay = next(backoff)
                logger.exception('Listener connection lost, reconnecting in %ds', delay)
                await asyncio.sleep(delay)
            finally:
                if connection and not connection.is_closed():
                    try:
                        await connection.close()
                    except Exception:
                        logger.warning(
                            'Failed to close asyncpg listener connection',
                            exc_info=True,
                        )

        logger.info('Stopped listening for connector_delivery notifications')

    def _on_delivery_notify(
        self,
        connection: asyncpg.Connection,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        message_uuid = payload
        logger.debug('Message %s scheduled for delivery', message_uuid)
        self._schedule_outbound_notification(message_uuid)

    def _schedule_outbound_notification(self, message_uuid: str) -> None:
        assert self._loop is not None
        task = self._loop.create_task(self._process_outbound_notification(message_uuid))
        self._in_flight.add(task)
        task.add_done_callback(self._task_done)

    async def _process_outbound_notification(self, message_uuid: str) -> None:
        async with self.semaphore:
            retry_delay: float | None = None
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

                    retry_delay = await self._executor.route_outbound(meta)
            except (StaleDataError, IntegrityError):
                logger.warning(
                    'Message %s was deleted during delivery, skipping',
                    message_uuid,
                )
                return
            except Exception:
                logger.exception(
                    'Failed to process delivery notification for %s', message_uuid
                )
                return

            if retry_delay is not None:
                self._schedule_outbound_later(retry_delay, message_uuid)

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
                self._schedule_outbound_later(delay, message_uuid)
            else:
                logger.info('Recovery: re-enqueuing %s immediately', message_uuid)
                self._schedule_outbound_notification(message_uuid)

    def _schedule_outbound_later(self, delay: float, message_uuid: str) -> None:
        """Schedule a delayed outbound notification; handle tracked for shutdown cancel."""
        assert self._loop is not None

        def fire() -> None:
            self._scheduled_timers.discard(handle)
            self._schedule_outbound_notification(message_uuid)

        handle = self._loop.call_later(delay, fire)
        self._scheduled_timers.add(handle)

    def resync_pollers(self) -> None:
        """Thread-safe: schedule a poller reconcile on the delivery loop."""
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(self._synchronize_pollers)

    def _synchronize_pollers(self) -> None:
        """Reconcile pollers against the store.

        Idempotent. Spawns pollers for poll-mode instances that are
        cached but unscheduled. Cancels pollers whose instance was
        evicted from the store (e.g. credential rotation).

        Mode is static config — not re-evaluated at runtime. This
        method handles only store-side churn.
        """
        connectors_config = self._config.get('connectors') or {}
        desired: dict[CacheKey, Connector] = {
            key: instance
            for key, instance in self._store.items()
            if (connectors_config.get(instance.backend) or {}).get('mode') == 'poll'
        }

        running = {k for k, t in self._pollers.items() if not t.done()}
        wanted = set(desired)

        for key in running - wanted:
            self._stop_poller(key)

        for key in wanted - running:
            self._pollers[key] = self.loop.create_task(
                self._run_poller(key, desired[key])
            )

    def _stop_poller(self, key: CacheKey) -> None:
        task = self._pollers.pop(key, None)
        if task and not task.done():
            task.cancel()

    async def _invoke_poll_method(self, fn: Any, *args: Any) -> Any:
        if inspect.iscoroutinefunction(fn):
            return await fn(*args)
        return await asyncio.to_thread(fn, *args)

    async def _run_poll_cycle(self, key: CacheKey, instance: Connector) -> bool:
        tenant_uuid, backend = key
        poll = False

        try:
            msgs = await self._invoke_poll_method(instance.scan_inbound)
            for msg in msgs:
                self.enqueue_message(msg)
            poll = poll or bool(msgs)
        except Exception:
            logger.exception('scan_inbound failed for %s', key)

        try:
            async with async_session_scope(self._session_factory):
                pending = await self._executor._room_dao.list_pending_external_ids(
                    tenant_uuid, backend
                )
            if pending:
                updates = await self._invoke_poll_method(
                    instance.track_outbound, pending
                )
                for update in updates:
                    self.enqueue_message(update)
                poll = poll or bool(updates)
        except Exception:
            logger.exception('track_outbound failed for %s', key)

        return poll

    async def _run_poller(self, key: CacheKey, instance: Connector) -> None:
        interval = self._poll_default
        try:
            while True:
                poll = await self._run_poll_cycle(key, instance)
                if poll:
                    interval = self._poll_min
                else:
                    interval = min(interval * 2, self._poll_max)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info('Poller for %s cancelled', key)
            raise

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
            self._healthy.set()

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


class ListenerRunner(Runner):
    """Dedicated runner for long-lived connector listener tasks.

    Isolated from :class:`DeliveryRunner` so a misbehaving listener
    (accidental blocking call, slow parser, deadlock) cannot stall
    outbound sends or webhook processing.

    Cross-thread message flow: listener tasks forward parsed events
    via the ``on_message`` callback (typically the delivery runner's
    ``enqueue_message``), which hops back via ``call_soon_threadsafe``
    — the same mechanism Flask uses for webhook inbound.
    """

    thread_name: ClassVar[str] = 'listener-runner'

    def __init__(
        self,
        config: ConfigDict,
        store: ConnectorStore,
        on_message: Callable[[InboundMessage | StatusUpdate], None],
    ) -> None:
        super().__init__()
        self._config = config
        self._store = store
        self._on_message = on_message
        self._listeners: dict[CacheKey, asyncio.Task[None]] = {}

    async def _on_start(self) -> None:
        try:
            await self._store.wait_populated()
        except Exception:
            logger.exception(
                '%s starting in degraded state: connector store populate failed',
                self.thread_name,
            )
        self._reconcile(self._build_desired())

    def _build_desired(self) -> dict[CacheKey, Connector]:
        connectors_config = self._config.get('connectors') or {}
        return {
            key: instance
            for key, instance in self._store.items()
            if (connectors_config.get(instance.backend) or {}).get('mode') == 'listen'
        }

    def synchronize(self, desired: dict[CacheKey, Connector]) -> None:
        """Reconcile listener tasks against *desired*.

        Idempotent. Thread-safe — schedules create/cancel on the
        listen loop via ``call_soon_threadsafe``.
        """
        self.loop.call_soon_threadsafe(self._reconcile, desired)

    def resync(self) -> None:
        """Thread-safe: reconcile against current store state."""
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        self.synchronize(self._build_desired())

    def _reconcile(self, desired: dict[CacheKey, Connector]) -> None:
        running = {k for k, t in self._listeners.items() if not t.done()}
        wanted = set(desired)

        for key in running - wanted:
            task = self._listeners.pop(key, None)
            if task and not task.done():
                task.cancel()

        for key in wanted - running:
            task = self.loop.create_task(desired[key].listen(self._on_message))
            task.add_done_callback(functools.partial(self._on_listener_done, key))
            self._listeners[key] = task

    def _on_listener_done(self, key: CacheKey, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error('Listener for %s crashed: %s', key, exc, exc_info=exc)

    async def _on_stop(self) -> None:
        for task in list(self._listeners.values()):
            if not task.done():
                task.cancel()
        if self._listeners:
            await asyncio.gather(*self._listeners.values(), return_exceptions=True)
        self._listeners.clear()
