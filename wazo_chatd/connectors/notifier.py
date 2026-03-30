# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from wazo_bus.resources.chatd.events import UserRoomMessageCreatedEvent
from wazo_bus.resources.common.event import ServiceEvent

from wazo_chatd.connectors.events import MessageDeliveryStatusEvent
from wazo_chatd.database.models import MessageMeta, Room, RoomMessage
from wazo_chatd.plugins.rooms.schemas import MessageSchema

if TYPE_CHECKING:
    from wazo_chatd.bus import BusPublisher

logger = logging.getLogger(__name__)


class AsyncNotifier:
    def __init__(self, bus_publisher: BusPublisher) -> None:
        self._bus = bus_publisher

    async def message_created(self, room: Room, message: RoomMessage) -> None:
        message_data = MessageSchema().dump(message)
        for user in room.users:
            event = UserRoomMessageCreatedEvent(
                message_data, room.uuid, room.tenant_uuid, user.uuid
            )
            await self._publish(event)

    async def delivery_status_updated(self, delivery: MessageMeta) -> None:
        message = delivery.message
        if not message:
            return

        room = message.room
        if not room:
            return

        user_uuids = [str(u.uuid) for u in room.users]
        delivery_data = {
            'message_uuid': str(delivery.message_uuid),
            'status': str(delivery.records[-1].status) if delivery.records else '',
            'backend': str(delivery.backend),
        }
        event = MessageDeliveryStatusEvent(
            delivery_data=delivery_data,
            tenant_uuid=str(room.tenant_uuid),
            user_uuids=user_uuids,
            room_uuid=str(room.uuid),
            message_uuid=str(delivery.message_uuid),
        )
        await self._publish(event)

    async def _publish(self, event: ServiceEvent) -> None:
        try:
            await asyncio.to_thread(self._bus.publish, event)
        except Exception:
            logger.exception('Failed to publish bus event %s', event.name)
