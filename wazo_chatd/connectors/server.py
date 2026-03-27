# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import enum
import logging
import multiprocessing as mp
import threading
import time
from multiprocessing.connection import Connection
from multiprocessing.context import SpawnProcess
from types import TracebackType
from typing import TYPE_CHECKING

from setproctitle import setproctitle
from xivo.xivo_logging import setup_logging

from wazo_chatd.connectors.executor import DeliveryExecutor
from wazo_chatd.connectors.registry import ConnectorRegistry
from wazo_chatd.connectors.types import (
    ConfigSync,
    ConfigUpdate,
    OutboundMessage,
    Ping,
    Pong,
    Ready,
)

if TYPE_CHECKING:
    from wazo_chatd.connectors.router import ConnectorRouter

WORKER_PROCESS_TITLE = 'wazo-chatd: connector worker'

logger = logging.getLogger(__name__)

_spawn = mp.get_context('spawn')

_MAX_RESTART_DELAY: int = 60
_HEALTH_CHECK_INTERVAL: float = 5.0
_PING_TIMEOUT: float = 3.0


class Sentinel(enum.Enum):
    SHUTDOWN = enum.auto()


PING = Ping()
PONG = Pong()
READY = Ready()

_WORKER_READY_TIMEOUT: float = 30.0


class MessageServer:
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
        self._queue: mp.Queue[OutboundMessage | Sentinel] = _spawn.Queue()
        self._main_connection: Connection | None = None
        self._worker_connection: Connection | None = None
        self._process: SpawnProcess | None = None
        self._pipe_lock = threading.Lock()
        self._stopped = False
        self._restart_count = 0
        self._watchdog: threading.Thread | None = None

    def __enter__(self) -> MessageServer:
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
        self._serve_forever()
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

    def _serve_forever(self) -> None:
        if self._process and self._process.is_alive():
            raise RuntimeError('Server is already running')

        self._main_connection, self._worker_connection = mp.Pipe()

        worker_args = (self._config, self._queue, self._worker_connection)
        self._process = _spawn.Process(
            target=MessageWorker.bootstrap,
            args=worker_args,
            name=WORKER_PROCESS_TITLE,
        )
        self._process.start()
        self._worker_connection.close()

    def shutdown(self, timeout: float = 10) -> None:
        self._stopped = True
        self._queue.put_nowait(Sentinel.SHUTDOWN)

        if self._process and self._process.is_alive():
            self._process.join(timeout=timeout)
            if self._process.is_alive():
                logger.warning('Worker did not stop gracefully, terminating')
                self._process.terminate()
                self._process.join(timeout=5)

    def send_message(
        self,
        message: OutboundMessage,
        delay: float | None = None,
    ) -> None:
        if delay:
            threading.Timer(delay, self._queue.put, args=(message,)).start()
        else:
            self._queue.put(message)

    def pipe_send(self, data: ConfigSync | ConfigUpdate) -> None:
        with self._pipe_lock:
            self.pipe.send(data)

    def ping(self, timeout: float = 5) -> bool:
        with self._pipe_lock:
            logger.debug("Server sending ping!")
            try:
                self.pipe.send(PING)
                if self.pipe.poll(timeout=timeout):
                    response = self.pipe.recv()
                    if response == PONG:
                        return True
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

            logger.debug('Sending health check ping to worker')
            if not self.ping(timeout=_PING_TIMEOUT):
                logger.error(
                    'Worker process unresponsive (ping timeout), restarting...'
                )
                self.shutdown(timeout=5)
                self._stopped = False
                self._restart_with_backoff()

    def _restart_with_backoff(self) -> None:
        delay = min(2**self._restart_count, _MAX_RESTART_DELAY)
        logger.info(
            'Restarting worker in %ds (attempt #%d)',
            delay,
            self._restart_count + 1,
        )
        time.sleep(delay)

        self._serve_forever()
        self._router.sync_to_server()
        self._restart_count += 1


class MessageWorker:
    """Runs inside the spawned process. Owns the asyncio loop and executor."""

    def __init__(
        self,
        queue: mp.Queue[OutboundMessage | Sentinel],
        connection: Connection,
        delivery_executor: DeliveryExecutor,
    ) -> None:
        self._queue = queue
        self._connection = connection
        self._delivery_executor = delivery_executor

    @property
    def pipe(self) -> Connection:
        return self._connection

    @staticmethod
    def bootstrap(
        config: dict[str, str | bool],
        queue: mp.Queue[OutboundMessage | Sentinel],
        connection: Connection,
    ) -> None:
        setproctitle(WORKER_PROCESS_TITLE)

        setup_logging(
            config.get('log_file', '/var/log/wazo-chatd.log'),  # type: ignore[arg-type]
            debug=bool(config.get('debug', False)),
        )
        logger.info('Worker process starting')

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

        worker = MessageWorker(queue, connection, delivery_executor)
        connection.send(READY)
        logger.info('Worker process ready, entering event loop')
        worker.run()

    def run(self) -> None:
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)
        try:
            event_loop.run_until_complete(self._run_tasks())
        finally:
            event_loop.close()
            logger.info('Worker process stopped')

    async def _run_tasks(self) -> None:
        pipe_task = asyncio.create_task(self._pipe_listener())
        queue_task = asyncio.create_task(self._queue_consumer())
        await queue_task
        pipe_task.cancel()

    async def _queue_consumer(self) -> None:
        while True:
            message = await asyncio.to_thread(self._queue.get)

            if message is Sentinel.SHUTDOWN:
                logger.info('Received shutdown sentinel')
                break

            logger.info(
                'Processing outbound message (delivery=%s)',
                message.delivery_uuid,
            )

    async def _pipe_listener(self) -> None:
        while True:
            has_data = await asyncio.to_thread(self.pipe.poll, 1.0)
            if has_data:
                self._handle_pipe_updates()

    def _handle_pipe_updates(self) -> None:
        while self.pipe.poll():
            command = self.pipe.recv()

            match command:
                case Ping():
                    self.pipe.send(PONG)

                case ConfigSync():
                    logger.info(
                        'Received config sync (%d providers)',
                        len(command.providers),
                    )
                    self._delivery_executor.load_from_pipe(command)

                case ConfigUpdate():
                    self._delivery_executor.handle_config_update(command)
