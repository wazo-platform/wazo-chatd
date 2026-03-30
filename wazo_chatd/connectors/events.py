# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from wazo_bus.resources.common.event import MultiUserEvent


class MessageDeliveryStatusEvent(MultiUserEvent):
    service = 'chatd'
    name = 'chatd_message_delivery_status'
    routing_key_fmt = 'chatd.rooms.{room_uuid}.messages.{message_uuid}.delivery'

    def __init__(
        self,
        delivery_data: dict[str, str],
        tenant_uuid: str,
        user_uuids: list[str],
        room_uuid: str,
        message_uuid: str,
    ) -> None:
        super().__init__(delivery_data, tenant_uuid, user_uuids)
        self.room_uuid = str(room_uuid)
        self.message_uuid = str(message_uuid)
