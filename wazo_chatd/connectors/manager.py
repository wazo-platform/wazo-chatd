# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import enum
import logging
import multiprocessing as mp
import os
import threading
import time
from multiprocessing.connection import Connection
from multiprocessing.context import SpawnProcess
from queue import Empty
from types import TracebackType
from typing import TYPE_CHECKING

from setproctitle import setproctitle
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import sessionmaker
from xivo.xivo_logging import setup_logging

from wazo_chatd.bus import BusPublisher
from wazo_chatd.connectors.executor import DeliveryExecutor
from wazo_chatd.database.async_helpers import async_session_scope, init_async_db
from wazo_chatd.connectors.registry import ConnectorRegistry
from wazo_chatd.connectors.types import (
    ConfigSync,
    ConfigUpdate,
    InboundMessage,
    OutboundMessage,
    Ping,
    PipeCommand,
    Pong,
    Ready,
)

if TYPE_CHECKING:
    from wazo_chatd.connectors.router import ConnectorRouter

WORKER_PROCESS_TITLE = 'wazo-chatd: connector worker'
PING = Ping()
PONG = Pong()
READY = Ready()

logger = logging.getLogger(__name__)

_spawn = mp.get_context('spawn')
_MAX_RESTART_DELAY: int = 60
_HEALTH_CHECK_INTERVAL: float = 5.0
_PING_TIMEOUT: float = 3.0
_WORKER_READY_TIMEOUT: float = 30.0


class Sentinel(enum.Enum):
    SHUTDOWN = enum.auto()
    EMPTY = enum.auto()


class DeliveryManager:
    """Manages the worker process for outbound message delivery.

    Owns the process lifecycle, queue, pipe, health monitoring via
    ping-pong, and automatic restart with backoff. Supports the
    context manager protocol for use with ExitStack.
    """

    def __init__(
        self,
        config: dict[str, str | bool],
        router: ConnectorRouter,
    ) -> None:
        self._config = config
        self._router = router
        self._queue: mp.Queue[OutboundMessage | InboundMessage | Sentinel] = (
            _spawn.Queue()
        )
        self._main_connection: Connection | None = None
        self._worker_connection: Connection | None = None
        self._process: SpawnProcess | None = None
        self._pipe_lock = threading.Lock()
        self._stopped = False
        self._restart_count = 0
        self._watchdog: threading.Thread | None = None

    def __enter__(self) -> DeliveryManager:
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
    def process(self) -> SpawnProcess | None:
        return self._process

    @property
    def restart_count(self) -> int:
        return self._restart_count

    @property
    def pipe(self) -> Connection:
        if self._main_connection is None:
            raise RuntimeError('Server has not been started yet')
        return self._main_connection

    def start(self) -> None:
        logger.info('Starting delivery manager')
        self._spawn_worker()
        self._router.sync_to_server()
        self._wait_for_ready()
        self._watchdog = threading.Thread(
            target=self._watch,
            name='connector-worker-watchdog',
            daemon=True,
        )
        self._watchdog.start()

    def _wait_for_ready(self) -> None:
        with self._pipe_lock:
            try:
                if self.pipe.poll(timeout=_WORKER_READY_TIMEOUT):
                    response = self.pipe.recv()
                    if response == READY:
                        logger.info('Worker process reported ready')
                        return
                logger.error(
                    'Worker did not report ready within %ds',
                    _WORKER_READY_TIMEOUT,
                )
            except (OSError, EOFError, RuntimeError):
                logger.error('Failed to receive ready signal from worker')

    def _spawn_worker(self) -> None:
        if self._process and self._process.is_alive():
            raise RuntimeError('Server is already running')

        self._main_connection, self._worker_connection = mp.Pipe()

        worker_args = (self._config, self._queue, self._worker_connection)
        self._process = _spawn.Process(
            target=_Worker.bootstrap,
            args=worker_args,
            name=WORKER_PROCESS_TITLE,
        )
        self._process.start()
        self._worker_connection.close()

    def shutdown(self, timeout: float = 10) -> None:
        logger.debug('Stopping delivery manager')
        self._stopped = True
        self._queue.put_nowait(Sentinel.SHUTDOWN)

        if self._process and self._process.is_alive():
            self._process.join(timeout=timeout)
            if self._process.is_alive():
                logger.warning('Worker did not stop gracefully, terminating')
                self._process.terminate()
                self._process.join(timeout=5)

        logger.info('Stopped delivery manager')

    def send_message(
        self,
        message: OutboundMessage,
        delay: float | None = None,
    ) -> None:
        if delay:
            threading.Timer(delay, self._queue.put, args=(message,)).start()
        else:
            self._queue.put(message)

    def send_inbound(self, message: InboundMessage) -> None:
        self._queue.put(message)

    def sync_config(self, providers: list[dict[str, str]]) -> None:
        self._pipe_send(ConfigSync(providers=providers))

    def _pipe_send(self, command: PipeCommand) -> None:
        with self._pipe_lock:
            self.pipe.send(command)

    def ping(self, timeout: float = 5) -> bool:
        with self._pipe_lock:
            logger.debug("Server: sending Ping!")
            try:
                self.pipe.send(PING)
                if self.pipe.poll(timeout=timeout):
                    response = self.pipe.recv()
                    return response == PONG
            except (OSError, EOFError, RuntimeError):
                pass
        return False

    def provide_status(self, status: dict[str, dict[str, str | int]]) -> None:
        process = self._process
        is_alive = process is not None and process.is_alive()
        is_responsive = is_alive and self.ping(timeout=2)
        status['message_worker'] = {
            'status': 'ok' if is_responsive else 'fail',
            'restart_count': self._restart_count,
        }

    def _watch(self) -> None:
        while not self._stopped:
            time.sleep(_HEALTH_CHECK_INTERVAL)
            if self._stopped:
                break

            process = self._process
            if process is None:
                continue

            if not process.is_alive():
                logger.error(
                    'Worker process died (exit code %s), restarting...',
                    process.exitcode,
                )
                self._restart_with_backoff()
                continue

            if not self.ping(timeout=_PING_TIMEOUT):
                logger.error(
                    'Worker process unresponsive (ping timeout), restarting...'
                )
                if self._process and self._process.is_alive():
                    self._process.terminate()
                    self._process.join(timeout=5)
                self._restart_with_backoff()

    def _restart_with_backoff(self) -> None:
        delay = min(2**self._restart_count, _MAX_RESTART_DELAY)
        logger.info(
            'Restarting worker in %ds (attempt #%d)',
            delay,
            self._restart_count + 1,
        )
        time.sleep(delay)

        self._spawn_worker()
        self._router.sync_to_server()
        self._wait_for_ready()
        self._restart_count += 1


class _Worker:
    def __init__(
        self,
        queue: mp.Queue[OutboundMessage | InboundMessage | Sentinel],
        connection: Connection,
        delivery_executor: DeliveryExecutor,
    ) -> None:
        self._queue = queue
        self._connection = connection
        self._delivery_executor = delivery_executor
        self._engine: AsyncEngine | None = None
        self._session_factory: sessionmaker | None = None
        self._bus_publisher: BusPublisher | None = None
        self._should_stop: asyncio.Future[None] | None = None

    def initialize(self, config: dict[str, str | bool]) -> None:
        db_uri = str(config.get('db_uri', ''))
        self._engine, self._session_factory = init_async_db(db_uri)
        logger.debug('Async database engine initialized')

        self._bus_publisher = BusPublisher.from_config(
            service_uuid=config.get('uuid', ''),
            bus_config=config.get('bus', {}),
        )
        logger.debug('Worker bus publisher initialized')

    @property
    def pipe(self) -> Connection:
        return self._connection

    @staticmethod
    def bootstrap(
        config: dict[str, str | bool],
        queue: mp.Queue[OutboundMessage | InboundMessage | Sentinel],
        connection: Connection,
    ) -> None:
        setproctitle(WORKER_PROCESS_TITLE)

        setup_logging(
            config.get('log_file', '/var/log/wazo-chatd.log'),  # type: ignore[arg-type]
            debug=bool(config.get('debug', False)),
        )
        logger.info('Worker process starting (pid: %d)', os.getpid())

        registry = ConnectorRegistry()
        registry.discover()
        logger.info(
            'Discovered %d connector backend(s): %s',
            len(registry.available_backends()),
            ', '.join(registry.available_backends()) or '(none)',
        )

        delivery_executor = DeliveryExecutor(registry=registry, connector_config={})

        if connection.poll(timeout=5):
            initial_config = connection.recv()
            if isinstance(initial_config, ConfigSync):
                logger.info(
                    'Loaded %d provider(s) from pipe',
                    len(initial_config.providers),
                )
                delivery_executor.load_from_pipe(initial_config)
        else:
            logger.info('No initial config received from pipe')

        worker = _Worker(queue, connection, delivery_executor)
        worker.initialize(config)
        connection.send(READY)

        logger.info('Worker process ready, entering event loop')
        worker.run()

    def run(self) -> None:
        asyncio.run(self._run_tasks())
        logger.info('Worker process stopped (pid: %d)', os.getpid())

    async def _run_tasks(self) -> None:
        self._should_stop = asyncio.Future()
        pipe_task = asyncio.create_task(self._pipe_listener())
        queue_task = asyncio.create_task(self._queue_consumer())

        try:
            await self._should_stop

            queue_task.cancel()
            pipe_task.cancel()
            for task in (queue_task, pipe_task):
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        finally:
            if self._engine:
                await self._engine.dispose()
                logger.debug('Async database engine disposed')

    async def _queue_get(self) -> OutboundMessage | InboundMessage | Sentinel:
        try:
            return await asyncio.to_thread(self._queue.get, True, 30.0)
        except Empty:
            return Sentinel.EMPTY

    async def _queue_consumer(self) -> None:
        assert self._should_stop is not None
        assert self._session_factory is not None

        while not self._should_stop.done():
            get_task = asyncio.create_task(self._queue_get())
            done, _ = await asyncio.wait(
                (get_task, self._should_stop),
                return_when=asyncio.FIRST_COMPLETED,
            )

            if self._should_stop in done:
                get_task.cancel()
                return

            message = get_task.result()
            match message:
                case Sentinel.EMPTY:
                    continue

                case Sentinel.SHUTDOWN:
                    logger.info('Received shutdown sentinel')
                    self._should_stop.set_result(None)
                    return

                case OutboundMessage():
                    logger.debug(
                        'Processing outbound message (message=%s)',
                        message.message_uuid,
                    )
                    async with async_session_scope(self._session_factory) as session:
                        await self._delivery_executor.route_outbound(
                            message,
                            session,
                            self._bus_publisher,
                        )

                case InboundMessage():
                    logger.debug(
                        'Processing inbound message (backend=%s)',
                        message.backend,
                    )
                    async with async_session_scope(self._session_factory) as session:
                        await self._delivery_executor.route_inbound(
                            message,
                            session,
                            self._bus_publisher,
                        )

    async def _pipe_listener(self) -> None:
        while True:
            has_data = await asyncio.to_thread(self.pipe.poll, 1.0)
            if not has_data:
                continue

            command = self.pipe.recv()

            match command:
                case Ping():
                    logger.debug('Worker: replying Pong!')
                    self.pipe.send(PONG)

                case ConfigSync():
                    logger.info(
                        'Received config sync (%d providers)',
                        len(command.providers),
                    )
                    self._delivery_executor.load_from_pipe(command)

                case ConfigUpdate():
                    self._delivery_executor.handle_config_update(command)
