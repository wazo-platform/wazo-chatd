# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Delivery executor — runs in the server (worker) process.

Uses asyncio for I/O-bound operations (DB writes, external API calls).
Sync connector implementations are wrapped with ``asyncio.to_thread()``.

The worker process should call :func:`set_worker_process_title` at
startup to give it a meaningful name in ``ps`` output (instead of the
default ``python -c multiprocessing...``).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

from wazo_chatd.connectors.connector import Connector
from wazo_chatd.connectors.delivery import (
    RETRY_DELAYS,
    DeliveryStatus,
    MAX_RETRIES,
)
from wazo_chatd.connectors.exceptions import ConnectorSendError
from wazo_chatd.connectors.registry import ConnectorRegistry
from wazo_chatd.connectors.types import ConfigSync, ConfigUpdate, OutboundMessage
from wazo_chatd.database.models import DeliveryRecord, MessageMeta

if TYPE_CHECKING:
    from sqlalchemy.orm import Session as SASession

    from wazo_chatd.bus import BusPublisher

logger = logging.getLogger(__name__)

WORKER_PROCESS_TITLE = 'wazo-chatd: connector worker'


def set_worker_process_title() -> None:
    """Set the worker process title for ``ps`` visibility.

    Call this at the start of the worker process entry point.
    Requires the ``setproctitle`` package (``python3-setproctitle``
    on Debian bookworm).
    """
    try:
        import setproctitle

        setproctitle.setproctitle(WORKER_PROCESS_TITLE)
    except ImportError:
        logger.debug('setproctitle not available, process title unchanged')


class DeliveryExecutor:
    """Executes connector send operations with delivery tracking and retries.

    Connectors are initialized locally from configuration received via
    pipe from the main process.  The executor never queries the DB for
    provider configuration — it only writes delivery status records.
    """

    def __init__(
        self,
        registry: ConnectorRegistry,
        connector_config: dict[str, str],
    ) -> None:
        self._registry = registry
        self._connector_config = connector_config
        self.connectors: dict[str, Connector] = {}

    def load_from_pipe(self, config_sync: ConfigSync) -> None:
        """Reconstruct connector instances from serialized config.

        Called during server process initialization with data received
        from the main process via pipe.
        """
        self.connectors.clear()
        for entry in config_sync.providers:
            name = entry['name']
            backend = entry['backend']
            try:
                cls = self._registry.get_backend(backend)
            except KeyError:
                logger.warning(
                    'Backend %r not available, skipping provider %r',
                    backend,
                    name,
                )
                continue

            instance = cls()
            instance.configure(
                entry['type'],
                entry.get('configuration', {}),
                self._connector_config,
            )
            self.connectors[name] = instance
            logger.info('Loaded connector instance %r (backend=%r)', name, backend)

    def handle_config_update(self, update: ConfigUpdate) -> None:
        """Apply a runtime configuration change from the main process."""
        name = update.provider.get('name', '')

        if update.action == 'remove':
            self.connectors.pop(name, None)
            logger.info('Removed connector instance %r', name)
            return

        backend = update.provider.get('backend', '')
        try:
            cls = self._registry.get_backend(backend)
        except KeyError:
            logger.warning(
                'Backend %r not available for config update on %r',
                backend,
                name,
            )
            return

        instance = cls()
        instance.configure(
            update.provider.get('type', ''),
            update.provider.get('configuration', {}),
            self._connector_config,
        )
        self.connectors[name] = instance
        logger.info('Updated connector instance %r (backend=%r)', name, backend)

    async def execute(
        self,
        outbound: OutboundMessage,
        delivery: MessageMeta,
        session: SASession,
        bus_publisher: BusPublisher,
    ) -> None:
        """Attempt to send a message and track the delivery lifecycle.

        Args:
            outbound: The message to send.
            delivery: The ``MessageMeta`` (or mock) for this delivery.
            session: The DB session for persisting ``DeliveryRecord`` rows.
            bus_publisher: The bus publisher for status event notifications.
        """
        connector = self._find_connector(delivery.backend)  # type: ignore[union-attr]
        if connector is None:
            self._add_record(
                session,
                delivery,
                DeliveryStatus.DEAD_LETTER,
                reason=f'Backend {delivery.backend!r} not available',  # type: ignore[union-attr]
            )
            return

        self._add_record(session, delivery, DeliveryStatus.SENDING)

        try:
            external_id = await self._send(connector, outbound)
            delivery.external_id = external_id  # type: ignore[union-attr]
            self._add_record(session, delivery, DeliveryStatus.SENT)

        except ConnectorSendError as exc:
            delivery.retry_count += 1  # type: ignore[union-attr]
            self._add_record(
                session, delivery, DeliveryStatus.FAILED, reason=str(exc),
            )

            if delivery.retry_count >= MAX_RETRIES:  # type: ignore[union-attr]
                self._add_record(
                    session,
                    delivery,
                    DeliveryStatus.DEAD_LETTER,
                    reason=f'Max retries ({MAX_RETRIES}) exceeded',
                )
            else:
                self._add_record(session, delivery, DeliveryStatus.RETRYING)

        await self._publish_status(bus_publisher, delivery)

    def _find_connector(self, backend: str) -> Connector | None:
        """Find a connector instance matching the given backend name."""
        for instance in self.connectors.values():
            if getattr(instance, 'backend', None) == backend:
                return instance
        return None

    async def _send(
        self, connector: Connector, outbound: OutboundMessage,
    ) -> str:
        """Call connector.send(), wrapping sync implementations."""
        if asyncio.iscoroutinefunction(connector.send):
            return await connector.send(outbound)  # type: ignore[misc]
        return await asyncio.to_thread(connector.send, outbound)

    async def _publish_status(
        self, bus_publisher: BusPublisher, delivery: MessageMeta,
    ) -> None:
        """Publish delivery status event to the bus.

        wazo-bus is sync-only, so we wrap with ``to_thread`` for v1.
        """
        # TODO: publish actual bus event when event classes are defined
        pass

    @staticmethod
    def _add_record(
        session: SASession,
        delivery: MessageMeta,
        status: DeliveryStatus,
        reason: str | None = None,
    ) -> None:
        """Append a delivery status record."""
        record = DeliveryRecord(
            message_uuid=delivery.message_uuid,  # type: ignore[union-attr]
            status=status.value,
            reason=reason,
        )
        session.add(record)  # type: ignore[union-attr]
        session.flush()  # type: ignore[union-attr]
