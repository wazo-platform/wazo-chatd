# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import enum
import logging
import multiprocessing as mp
import threading
from multiprocessing.connection import Connection
from multiprocessing.context import SpawnProcess

from setproctitle import setproctitle

from wazo_chatd.connectors.executor import DeliveryExecutor
from wazo_chatd.connectors.registry import ConnectorRegistry
from wazo_chatd.connectors.types import ConfigSync, ConfigUpdate, OutboundMessage

WORKER_PROCESS_TITLE = 'wazo-chatd: connector worker'

logger = logging.getLogger(__name__)

_spawn = mp.get_context('spawn')


class Sentinel(enum.Enum):
    SHUTDOWN = enum.auto()


class HealthCheck(enum.Enum):
    PING = enum.auto()
    PONG = enum.auto()


class MessageServer:
    """Manages the worker process for outbound message delivery."""

    def __init__(self) -> None:
        self._queue: mp.Queue[OutboundMessage | Sentinel] = _spawn.Queue()
        self._main_connection, self._worker_connection = mp.Pipe()
        self._process: SpawnProcess | None = None

    @property
    def process(self) -> SpawnProcess | None:
        return self._process

    def serve_forever(self) -> None:
        if self._process and self._process.is_alive():
            raise RuntimeError('Server is already running')

        worker_args = (self._queue, self._worker_connection)
        self._process = _spawn.Process(
            target=MessageWorker.bootstrap,
            args=worker_args,
            name=WORKER_PROCESS_TITLE,
        )
        self._process.start()
        self._worker_connection.close()

    def shutdown(self, timeout: float = 10) -> None:
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
        self._main_connection.send(data)

    def ping(self, timeout: float = 5) -> bool:
        """Send a ping to the worker and wait for a pong.

        Returns True if the worker responded within the timeout.
        """
        try:
            self._main_connection.send(HealthCheck.PING)
            if self._main_connection.poll(timeout=timeout):
                response = self._main_connection.recv()
                return response is HealthCheck.PONG
        except (OSError, EOFError):
            pass
        return False


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

    @staticmethod
    def bootstrap(
        queue: mp.Queue[OutboundMessage | Sentinel],
        connection: Connection,
    ) -> None:
        setproctitle(WORKER_PROCESS_TITLE)

        logging.basicConfig(level=logging.INFO)
        logger.info('Worker process starting (pid=%d)', mp.current_process().pid)

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
        logger.info('Worker process ready, entering event loop')
        worker.run()

    def run(self) -> None:
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)
        try:
            event_loop.run_until_complete(self._process_loop())
        finally:
            event_loop.close()
            logger.info('Worker process stopped')

    async def _process_loop(self) -> None:
        while True:
            logger.debug('Waiting for next message...')
            message = await asyncio.to_thread(self._queue.get)

            if message is Sentinel.SHUTDOWN:
                logger.info('Received shutdown sentinel')
                break

            self._handle_pipe_updates()
            logger.info(
                'Processing outbound message (delivery=%s)',
                message.delivery_uuid,
            )

    def _handle_pipe_updates(self) -> None:
        while self._connection.poll():
            update = self._connection.recv()
            if update is HealthCheck.PING:
                logger.debug('Received ping, sending pong')
                self._connection.send(HealthCheck.PONG)
            elif isinstance(update, ConfigSync):
                logger.info(
                    'Received config sync (%d providers)', len(update.providers)
                )
                self._delivery_executor.load_from_pipe(update)
            elif isinstance(update, ConfigUpdate):
                self._delivery_executor.handle_config_update(update)
