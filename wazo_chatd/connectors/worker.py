# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import logging
import multiprocessing as mp
import os
from multiprocessing.connection import Connection
from queue import Empty

from setproctitle import setproctitle
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import sessionmaker
from xivo.xivo_logging import setup_logging

from wazo_chatd.bus import BusPublisher
from wazo_chatd.connectors.executor import DeliveryExecutor
from wazo_chatd.connectors.notifier import AsyncNotifier
from wazo_chatd.connectors.registry import ConnectorRegistry
from wazo_chatd.connectors.types import (
    ConfigSync,
    ConfigUpdate,
    InboundMessage,
    OutboundMessage,
    Ping,
    Pong,
    Ready,
    Sentinel,
)
from wazo_chatd.database.async_helpers import async_session_scope, init_async_db

PONG = Pong()
READY = Ready()
logger = logging.getLogger(__name__)


def worker_entrypoint(
    config: dict[str, str | bool],
    queue: mp.Queue[OutboundMessage | InboundMessage | Sentinel],
    connection: Connection,
) -> None:
    setup_logging(
        config.get('log_file', '/var/log/wazo-chatd.log'),  # type: ignore[arg-type]
        debug=bool(config.get('debug', False)),
    )

    worker = Worker(queue, connection)
    worker.bootstrap(config)
    worker.wait_for_config()
    worker.report_ready()
    worker.run()


class Worker:
    PROCESS_TITLE = 'wazo-chatd: connector worker'

    def __init__(
        self,
        queue: mp.Queue[OutboundMessage | InboundMessage | Sentinel],
        connection: Connection,
    ) -> None:
        self._queue = queue
        self._connection = connection
        self._delivery_executor: DeliveryExecutor | None = None
        self._engine: AsyncEngine | None = None
        self._session_factory: sessionmaker | None = None
        self._notifier: AsyncNotifier | None = None
        self._should_stop: asyncio.Future[None] | None = None

    @property
    def executor(self) -> DeliveryExecutor:
        if self._delivery_executor is None:
            raise RuntimeError('Worker not bootstrapped')
        return self._delivery_executor

    @property
    def pipe(self) -> Connection:
        return self._connection

    @property
    def session_factory(self) -> sessionmaker:
        if self._session_factory is None:
            raise RuntimeError('Worker not bootstrapped')
        return self._session_factory

    def bootstrap(self, config: dict[str, str | bool]) -> None:
        setproctitle(self.PROCESS_TITLE)
        logger.info('Worker process starting (pid: %d)', os.getpid())

        registry = ConnectorRegistry()
        registry.discover()
        logger.info(
            'Discovered %d connector backend(s): %s',
            len(registry.available_backends()),
            ', '.join(registry.available_backends()) or '(none)',
        )

        db_uri = str(config.get('db_uri', ''))
        self._engine, self._session_factory = init_async_db(db_uri)
        logger.debug('Async database engine initialized')

        bus_publisher = BusPublisher.from_config(
            service_uuid=config.get('uuid', ''),
            bus_config=config.get('bus', {}),
        )
        self._notifier = AsyncNotifier(bus_publisher)
        logger.debug('Worker bus publisher initialized')

        self._delivery_executor = DeliveryExecutor(
            registry=registry, connector_config={}, notifier=self._notifier
        )

    def wait_for_config(self) -> None:
        if self.pipe.poll(timeout=5):
            initial_config = self.pipe.recv()
            if isinstance(initial_config, ConfigSync):
                logger.info(
                    'Loaded %d provider(s) from pipe',
                    len(initial_config.providers),
                )
                self.executor.load_from_pipe(initial_config)
        else:
            logger.info('No initial config received from pipe')

    def report_ready(self) -> None:
        self._connection.send(READY)
        logger.info('Worker process ready, entering event loop')

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
                    async with async_session_scope(self.session_factory):
                        await self.executor.route_outbound(message)

                case InboundMessage():
                    logger.debug(
                        'Processing inbound message (backend=%s)',
                        message.backend,
                    )
                    async with async_session_scope(self.session_factory):
                        await self.executor.route_inbound(message)

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
                    self.executor.load_from_pipe(command)

                case ConfigUpdate():
                    self.executor.handle_config_update(command)
