# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import abc
import asyncio
import concurrent.futures
import functools
import itertools
import logging
import threading
from collections.abc import Callable, Coroutine, Iterable
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
from wazo_chatd.plugins.connectors.exceptions import ConnectorRateLimited
from wazo_chatd.plugins.connectors.executor import MAX_RETRY_AFTER, DeliveryExecutor
from wazo_chatd.plugins.connectors.notifier import AsyncNotifier
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.store import CacheKey, ConnectorStore
from wazo_chatd.plugins.connectors.types import InboundMessage, StatusUpdate

logger = logging.getLogger(__name__)

LISTEN_PING_INTERVAL: float = 30.0
LISTEN_PING_TIMEOUT: float = 10.0


def _backoff() -> itertools.chain[int]:
    return itertools.chain([1, 2, 4, 8, 16, 32], itertools.repeat(32))


async def _cancel_and_gather(tasks: Iterable[asyncio.Task[None]]) -> None:
    """Cancel any unfinished task and gather their results, swallowing exceptions."""
    pending = [t for t in tasks if not t.done()]
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def _observe_future(
    source: concurrent.futures.Future[None],
    loop: asyncio.AbstractEventLoop,
) -> asyncio.Future[None]:
    """
    Read-only asyncio.Future that resolves when ``source`` completes;
    cancelling the returned future does not cancel ``source``.
    """
    target: asyncio.Future[None] = loop.create_future()
    if source.done():
        target.set_result(None)
        return target

    def _mark_done() -> None:
        if not target.done():
            target.set_result(None)

    def _on_source_done(_: concurrent.futures.Future[None]) -> None:
        loop.call_soon_threadsafe(_mark_done)

    source.add_done_callback(_on_source_done)
    return target


class Runner(abc.ABC):
    """Event loop running on a dedicated daemon thread.

    Handles thread + loop lifecycle (via :func:`asyncio.run`), crash
    recovery with iterative exponential backoff, and a
    loop-independent close signal that survives restarts.

    :meth:`start` spawns the thread; :meth:`shutdown` signals
    ``_closing`` and joins.

    Subclasses implement :meth:`_run` — a coroutine that owns the
    full lifecycle (setup, steady state, cleanup via ``try/finally``).
    The base races it against the close signal and cancels it on
    shutdown; any exception from :meth:`_run` propagates so the
    thread loop triggers a restart.
    """

    thread_name: ClassVar[str] = 'runner'
    start_timeout: ClassVar[float] = 10.0
    shutdown_timeout: ClassVar[float] = 30.0

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = threading.Thread(
            target=self._thread_target, name=self.thread_name, daemon=True
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

    def _thread_target(self) -> None:
        """Thread target: drive the async lifecycle and restart on crash."""
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
        run_task: asyncio.Task[None] = asyncio.create_task(self._run())
        closing = _observe_future(self._closing, self._loop)

        try:
            done, _ = await asyncio.wait(
                [run_task, closing],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if run_task in done and not run_task.cancelled():
                if (exc := run_task.exception()) is not None:
                    raise exc
        finally:
            if not run_task.done():
                run_task.cancel()
                try:
                    await run_task
                except (asyncio.CancelledError, Exception):
                    pass

    def start(self) -> None:
        if self._thread.is_alive() or self._thread.ident is not None:
            raise RuntimeError(f'{type(self).__name__} already started')
        logger.info('Starting %s', self.thread_name)
        self._thread.start()
        if not self._ready.wait(timeout=self.start_timeout):
            raise RuntimeError(
                f'{type(self).__name__} failed to start within '
                f'{self.start_timeout}s'
            )
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
        await _observe_future(self._closing, self.loop)

    @abc.abstractmethod
    async def _run(self) -> None:
        """Implement the runner lifecycle.

        The base spawns this as a task and races it against the
        ``_closing`` shutdown signal. On shutdown the base cancels
        this coroutine, raising :class:`asyncio.CancelledError` —
        cleanup belongs in a ``finally`` block::

            async def _run(self):
                resource = await self._setup()
                try:
                    # block on work until shutdown cancels us, or
                    # until a critical task crashes
                    await self._wait_closing()
                finally:
                    await resource.close()

        Subclasses determine task criticality on their own: re-raise
        a critical task's exception from inside this method to trigger
        the runner's restart path.
        """


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

        self._tasks: dict[tuple[str, ...], asyncio.Task[None]] = {}
        self._semaphore: asyncio.Semaphore | None = None
        self._outbound_notify_task: asyncio.Task[None] | None = None
        self._pollers: dict[CacheKey, asyncio.Task[None]] = {}
        self._queue: AsyncQueue[InboundMessage | StatusUpdate] = AsyncQueue()
        self._dispatch_task: asyncio.Task[None] | None = None
        self._scheduled_timers: set[asyncio.TimerHandle] = set()
        self._scheduled_outbound_timers: dict[str, asyncio.TimerHandle] = {}

    @property
    def semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            raise RuntimeError('DeliveryRunner has not been started')
        return self._semaphore

    @property
    def in_flight_count(self) -> int:
        return len(self._tasks)

    def enqueue_message(self, message: InboundMessage | StatusUpdate) -> None:
        try:
            self._queue.append(message)
        except QueueFull:
            logger.warning(
                'Delivery queue full (%d), dropping %s',
                len(self._queue),
                message,
            )

    def resync_pollers(self) -> None:
        """Thread-safe: schedule a poller reconcile on the delivery loop."""
        try:
            self.loop.call_soon_threadsafe(self._synchronize_pollers)
        except RuntimeError:
            pass

    def _reset_loop_state(self) -> None:
        """Drop state bound to the previous event loop so restarts are clean."""
        self._tasks = {}
        self._pollers = {}
        self._scheduled_timers = set()
        self._scheduled_outbound_timers = {}
        self._queue.reset()
        self._semaphore = asyncio.Semaphore(self._max_tasks)
        self._outbound_notify_task = None
        self._dispatch_task = None

    async def _run(self) -> None:
        self._reset_loop_state()
        try:
            await self._store.wait_populated()
        except Exception:
            logger.exception(
                '%s starting in degraded state: connector store populate failed',
                self.thread_name,
            )

        self._outbound_notify_task = asyncio.create_task(self._listen_for_deliveries())
        self._dispatch_task = asyncio.create_task(self._dispatch())
        self._synchronize_pollers()
        critical_tasks = (self._outbound_notify_task, self._dispatch_task)

        try:
            done, _ = await asyncio.wait(
                critical_tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                if task.cancelled():
                    continue
                if (exc := task.exception()) is not None:
                    raise exc
        finally:
            await self._shutdown(critical_tasks)

    async def _shutdown(self, critical_tasks: tuple[asyncio.Task[None], ...]) -> None:
        await _cancel_and_gather(critical_tasks)
        await _cancel_and_gather(self._pollers.values())
        self._pollers.clear()

        for handle in self._scheduled_timers:
            handle.cancel()

        self._scheduled_timers.clear()

        if self._tasks:
            logger.info(
                'Waiting for %d in-flight task(s) to complete', len(self._tasks)
            )
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)

        self._tasks.clear()

        if self.is_closing and self._engine:
            await self._engine.dispose()
            logger.debug('Async database engine disposed')

    async def _listen_for_deliveries(self) -> None:
        backoff = _backoff()

        try:
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

                    await self._monitor_listen_connection(connection)
                except Exception:
                    delay = next(backoff)
                    logger.exception(
                        'Listener connection lost, reconnecting in %ds', delay
                    )
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
        finally:
            logger.info('Stopped listening for connector_delivery notifications')

    async def _monitor_listen_connection(self, connection: asyncpg.Connection) -> None:
        closing_task = asyncio.create_task(self._wait_closing())

        try:
            while not self.is_closing:
                done, _ = await asyncio.wait(
                    {closing_task},
                    timeout=LISTEN_PING_INTERVAL,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if closing_task in done:
                    return

                await asyncio.wait_for(
                    connection.execute('SELECT 1'),
                    timeout=LISTEN_PING_TIMEOUT,
                )
        finally:
            if not closing_task.done():
                closing_task.cancel()
                try:
                    await closing_task
                except asyncio.CancelledError:
                    if (current := asyncio.current_task()) and current.cancelling():
                        raise

    def _on_delivery_notify(
        self,
        _connection: asyncpg.Connection,
        _pid: int,
        _channel: str,
        payload: str,
    ) -> None:
        for delivery_id in payload.split(','):
            if delivery_id:
                self._schedule_outbound_delivery(delivery_id)

    async def _recover(self) -> None:
        try:
            async with async_session_scope(self._session_factory):
                recoverable = await self._executor.recover_pending_deliveries()
        except Exception:
            logger.exception('Recovery scan failed, continuing without recovery')
            return

        for delivery_id, delay in recoverable:
            if delay > 0:
                logger.info(
                    'Recovery: re-enqueuing delivery %s with %.0fs delay',
                    delivery_id,
                    delay,
                )
                self._schedule_outbound_delivery_later(delay, delivery_id)
            else:
                logger.info(
                    'Recovery: re-enqueuing delivery %s immediately', delivery_id
                )
                self._schedule_outbound_delivery(delivery_id)

    def _schedule_outbound_delivery(self, delivery_id: str) -> None:
        if (key := ('outbound_delivery', delivery_id)) in self._tasks:
            return

        task = self.loop.create_task(self._process_outbound_delivery(delivery_id))
        self._tasks[key] = task
        task.add_done_callback(self._mark_healthy)
        task.add_done_callback(lambda _t: self._tasks.pop(key, None))

    def _schedule_outbound_delivery_later(self, delay: float, delivery_id: str) -> None:
        if (existing := self._scheduled_outbound_timers.get(delivery_id)) is not None:
            existing.cancel()
            self._scheduled_timers.discard(existing)

        def callback() -> None:
            self._scheduled_timers.discard(handle)
            self._scheduled_outbound_timers.pop(delivery_id, None)
            self._schedule_outbound_delivery(delivery_id)

        handle = self.loop.call_later(delay, callback)
        self._scheduled_timers.add(handle)
        self._scheduled_outbound_timers[delivery_id] = handle

    async def _process_outbound_delivery(self, delivery_id: str) -> None:
        async with self.semaphore:
            retry_delay: float | None = None
            try:
                async with async_session_scope(self._session_factory):
                    retry_delay = await self._executor.route_outbound_delivery(
                        delivery_id
                    )
            except (StaleDataError, IntegrityError):
                logger.warning(
                    'Delivery %s was deleted before dispatch, skipping', delivery_id
                )
                return
            except Exception:
                logger.exception('Failed to process outbound delivery %s', delivery_id)
                return

            if retry_delay is not None:
                self._schedule_outbound_delivery_later(retry_delay, delivery_id)

    async def _dispatch(self) -> None:
        async for message in self._queue:
            self._schedule_inbound(message)

    def _schedule_inbound(
        self,
        message: InboundMessage | StatusUpdate,
        *,
        attempt: int = 0,
    ) -> None:
        key: tuple[str, ...]
        match message:
            case InboundMessage() as m:
                key = ('inbound', m.backend, m.external_id, str(attempt))
                if key in self._tasks:
                    return
                coro = self._executor.route_inbound(message, attempt=attempt)

            case StatusUpdate() as m:
                key = ('status', m.backend, m.external_id, m.status, str(attempt))
                if key in self._tasks:
                    return
                coro = self._executor.route_status_update(message, attempt=attempt)

            case _:
                logger.warning(
                    'Unknown message type in delivery queue: %s',
                    type(message).__name__,
                )
                return

        task = self.loop.create_task(self._process(coro, message, attempt))
        self._tasks[key] = task
        task.add_done_callback(self._mark_healthy)
        task.add_done_callback(lambda _t: self._tasks.pop(key, None))

    def _schedule_inbound_later(
        self,
        delay: float,
        message: InboundMessage | StatusUpdate,
        attempt: int,
    ) -> None:
        def callback() -> None:
            self._scheduled_timers.discard(handle)
            self._schedule_inbound(message, attempt=attempt)

        handle = self.loop.call_later(delay, callback)
        self._scheduled_timers.add(handle)

    async def _process(
        self,
        coro: Coroutine[Any, Any, float | None],
        message: InboundMessage | StatusUpdate,
        attempt: int,
    ) -> None:
        async with self.semaphore:
            logger.debug('Processing %s', message)
            try:
                async with async_session_scope(self._session_factory):
                    retry_delay = await coro
            except Exception:
                logger.exception('Failed to process %s', message)
                return

        if retry_delay is not None:
            self._schedule_inbound_later(retry_delay, message, attempt + 1)

    def _synchronize_pollers(self) -> None:
        """Reconcile pollers against the store.

        Idempotent. Spawns pollers for poll-mode instances that are
        cached but unscheduled. Cancels pollers whose instance was
        evicted from the store (e.g. credential rotation).

        Mode is static config — not re-evaluated at runtime. This
        method handles only store-side churn.
        """
        for key in list(self._pollers):
            task = self._pollers[key]
            if not task.done():
                continue
            if not task.cancelled() and (exc := task.exception()) is not None:
                logger.error(
                    'Poller for %s exited with %s: %s',
                    key,
                    type(exc).__name__,
                    exc,
                    exc_info=exc,
                )
            del self._pollers[key]

        connectors_config = self._config.get('connectors') or {}
        desired: dict[CacheKey, Connector] = {
            key: instance
            for key, instance in self._store.items()
            if (connectors_config.get(instance.backend) or {}).get('mode') == 'poll'
        }

        running = set(self._pollers)
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

    async def _run_poller(self, key: CacheKey, instance: Connector) -> None:
        tenant_uuid, backend = key
        interval = self._poll_default
        while True:
            try:
                yielded = await self._scan_inbound(instance, key)
                yielded |= await self._track_outbound(instance, tenant_uuid, backend)
                interval = (
                    self._poll_min if yielded else min(interval * 2, self._poll_max)
                )
            except asyncio.CancelledError:
                logger.info('Poller for %s cancelled', key)
                raise
            except ConnectorRateLimited as exc:
                interval = min(exc.retry_after, MAX_RETRY_AFTER)
                logger.info('Poller for %s rate-limited, sleeping %.1fs', key, interval)
            except Exception:
                logger.exception('Poller for %s hit unexpected error, continuing', key)
                interval = min(interval * 2, self._poll_max)
            await asyncio.sleep(interval)

    async def _scan_inbound(self, instance: Connector, key: CacheKey) -> bool:
        try:
            messages = await self._invoke_poll_method(instance.scan_inbound)
        except ConnectorRateLimited:
            raise
        except Exception:
            logger.exception('scan_inbound failed for %s', key)
            return False
        for message in messages:
            self.enqueue_message(message)
        return bool(messages)

    async def _track_outbound(
        self, instance: Connector, tenant_uuid: str, backend: str
    ) -> bool:
        try:
            async with async_session_scope(self._session_factory):
                pending = await self._executor.list_pending_external_ids(
                    tenant_uuid, backend
                )
            if not pending:
                return False
            updates = await self._invoke_poll_method(instance.track_outbound, pending)
        except ConnectorRateLimited:
            raise
        except Exception:
            logger.exception('track_outbound failed for %s', (tenant_uuid, backend))
            return False
        for update in updates:
            self.enqueue_message(update)
        return bool(updates)

    async def _invoke_poll_method(self, fn: Any, *args: Any) -> Any:
        if asyncio.iscoroutinefunction(fn):
            return await fn(*args)
        return await asyncio.to_thread(fn, *args)

    def _mark_healthy(self, task: asyncio.Task[None]) -> None:
        if not task.cancelled() and task.exception() is None:
            self._healthy.set()


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

    async def _run(self) -> None:
        try:
            await self._store.wait_populated()
        except Exception:
            logger.exception(
                '%s starting in degraded state: connector store populate failed',
                self.thread_name,
            )
        self._reconcile(self._build_desired())

        try:
            await self._wait_closing()
        finally:
            await _cancel_and_gather(self._listeners.values())
            self._listeners.clear()

    def _build_desired(self) -> dict[CacheKey, Connector]:
        connectors_config = self._config.get('connectors') or {}
        return {
            key: instance
            for key, instance in self._store.items()
            if (connectors_config.get(instance.backend) or {}).get('mode') == 'listen'
        }

    def resync(self) -> None:
        """Thread-safe: reconcile listener tasks against current store state."""
        try:
            self.loop.call_soon_threadsafe(self._reconcile, self._build_desired())
        except RuntimeError:
            pass

    def _reconcile(self, desired: dict[CacheKey, Connector]) -> None:
        for key in list(self._listeners):
            task = self._listeners[key]
            if not task.done():
                continue
            if not task.cancelled() and (exc := task.exception()) is not None:
                logger.error(
                    'Listener for %s exited with %s: %s',
                    key,
                    type(exc).__name__,
                    exc,
                    exc_info=exc,
                )
            del self._listeners[key]

        running = set(self._listeners)
        wanted = set(desired)

        for key in running - wanted:
            task = self._listeners.pop(key)
            if not task.done():
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


class NullRunner:
    """Null Object stand-in used when no connector backends are registered.

    Implements the union of :class:`DeliveryRunner` and :class:`ListenerRunner`
    surfaces touched by :class:`ConnectorRouter` so callers don't need to
    branch on absence.
    """

    is_running = True
    in_flight_count = 0
    restart_count = 0

    def start(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def resync_pollers(self) -> None:
        pass

    def resync(self) -> None:
        pass

    def enqueue_message(self, _msg: InboundMessage | StatusUpdate) -> None:
        pass
