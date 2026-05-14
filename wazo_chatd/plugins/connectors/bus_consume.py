# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wazo_chatd.bus import BusConsumer
    from wazo_chatd.plugins.connectors.router import ConnectorRouter

logger = logging.getLogger(__name__)


class BusEventHandler:
    def __init__(self, bus: BusConsumer, router: ConnectorRouter) -> None:
        self.bus = bus
        self.router = router

    def subscribe(self) -> None:
        events = (
            ('auth_external_auth_added', self.on_external_auth_changed),
            ('auth_external_auth_updated', self.on_external_auth_changed),
            ('auth_external_auth_deleted', self.on_external_auth_changed),
        )
        for event, handler in events:
            self.bus.subscribe(event, handler)

    def on_external_auth_changed(self, payload: dict) -> None:
        tenant_uuid = payload['uuid']
        backend = payload['external_auth_name']
        logger.debug(
            'Invalidating connector cache for tenant=%s backend=%s',
            tenant_uuid,
            backend,
        )
        self.router.invalidate_backend_cache(tenant_uuid, backend)
