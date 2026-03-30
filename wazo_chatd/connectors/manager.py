# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
import multiprocessing as mp
import threading
import time
from multiprocessing.connection import Connection
from multiprocessing.context import SpawnProcess
from types import TracebackType
from typing import TYPE_CHECKING

from wazo_chatd.connectors.types import (
    ConfigSync,
    InboundMessage,
    OutboundMessage,
    Ping,
    Pong,
    PipeCommand,
    Ready,
    Sentinel,
)
from wazo_chatd.connectors.worker import Worker, worker_entrypoint

if TYPE_CHECKING:
    from wazo_chatd.connectors.router import ConnectorRouter

PING = Ping()
PONG = Pong()
READY = Ready()

logger = logging.getLogger(__name__)

_spawn = mp.get_context('spawn')
_MAX_RESTART_DELAY: int = 60
_HEALTH_CHECK_INTERVAL: float = 5.0
_PING_TIMEOUT: float = 3.0
_WORKER_READY_TIMEOUT: float = 30.0


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
    def pipe(self) -> Connection:
        if self._main_connection is None:
            raise RuntimeError('Server has not been started yet')
        return self._main_connection

    @property
    def process(self) -> SpawnProcess | None:
        return self._process

    @property
    def restart_count(self) -> int:
        return self._restart_count

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

    def enqueue_message(
        self,
        message: OutboundMessage | InboundMessage,
        delay: float | None = None,
    ) -> None:
        if delay:
            threading.Timer(delay, self._queue.put, args=(message,)).start()
        else:
            self._queue.put(message)

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

    def start(self) -> None:
        logger.info('Starting delivery manager')
        self._spawn_worker()
        self._router.sync_to_server()
        self._wait_worker_ready()
        self._watchdog = threading.Thread(
            target=self._monitor_worker,
            name='connector-worker-watchdog',
            daemon=True,
        )
        self._watchdog.start()

    def sync_config(self, providers: list[dict[str, str]]) -> None:
        self._pipe_send(ConfigSync(providers=providers))

    def _pipe_send(self, command: PipeCommand) -> None:
        with self._pipe_lock:
            self.pipe.send(command)

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
        self._wait_worker_ready()
        self._restart_count += 1

    def _spawn_worker(self) -> None:
        if self._process and self._process.is_alive():
            raise RuntimeError('Server is already running')

        self._main_connection, self._worker_connection = mp.Pipe()

        worker_args = (self._config, self._queue, self._worker_connection)
        self._process = _spawn.Process(
            target=worker_entrypoint,
            args=worker_args,
            name=Worker.PROCESS_TITLE,
        )
        self._process.start()
        self._worker_connection.close()

    def _wait_worker_ready(self) -> None:
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

    def _monitor_worker(self) -> None:
        while not self._stopped:
            time.sleep(_HEALTH_CHECK_INTERVAL)
            if self._stopped:
                break

            process = self.process
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
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
                self._restart_with_backoff()
