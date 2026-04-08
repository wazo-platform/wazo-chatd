# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from wazo_bus.resources.chatd.events import (
    MessageDeliveryStatusEvent,
    UserIdentityCreatedEvent,
    UserIdentityDeletedEvent,
    UserIdentityUpdatedEvent,
    UserRoomMessageCreatedEvent,
)
from wazo_bus.resources.chatd.types import MessageDict
from wazo_bus.resources.common.event import ServiceEvent

from wazo_chatd.database.models import Room, RoomMessage, UserIdentity
from wazo_chatd.plugins.connectors.schemas import UserIdentitySchema

if TYPE_CHECKING:
    from wazo_chatd.bus import BusPublisher

logger = logging.getLogger(__name__)


class UserIdentityNotifier:
    def __init__(self, bus_publisher: BusPublisher) -> None:
        self._bus = bus_publisher

    def created(self, identity: UserIdentity) -> None:
        identity_data = UserIdentitySchema().dump(identity)
        event = UserIdentityCreatedEvent(
            identity_data, str(identity.tenant_uuid), str(identity.user_uuid)
        )
        self._bus.publish(event)

    def updated(self, identity: UserIdentity) -> None:
        identity_data = UserIdentitySchema().dump(identity)
        event = UserIdentityUpdatedEvent(
            identity_data, str(identity.tenant_uuid), str(identity.user_uuid)
        )
        self._bus.publish(event)

    def deleted(self, identity: UserIdentity) -> None:
        identity_data = UserIdentitySchema().dump(identity)
        event = UserIdentityDeletedEvent(
            identity_data, str(identity.tenant_uuid), str(identity.user_uuid)
        )
        self._bus.publish(event)


class AsyncNotifier:
    def __init__(self, bus_publisher: BusPublisher) -> None:
        self._bus = bus_publisher

    async def message_created(self, room: Room, message: RoomMessage) -> None:
        message_data: MessageDict = {
            'uuid': str(message.uuid),
            'content': message.content,
            'alias': message.alias,
            'type': str(message.meta.type_),
            'backend': str(message.meta.backend),
            'user_uuid': str(message.user_uuid),
            'tenant_uuid': str(message.tenant_uuid),
            'wazo_uuid': str(message.wazo_uuid),
            'created_at': message.created_at.isoformat(),
            'room': {'uuid': str(message.room.uuid)},
        }
        for user in room.users:
            event = UserRoomMessageCreatedEvent(
                message_data, room.uuid, room.tenant_uuid, user.uuid
            )
            await self._publish(event)

    async def delivery_status_updated(
        self,
        message_uuid: str,
        status: str,
        timestamp: str,
        backend: str,
        tenant_uuid: str,
        room_uuid: str,
        user_uuids: list[str],
    ) -> None:
        delivery_data = {
            'message_uuid': message_uuid,
            'status': status,
            'timestamp': timestamp,
            'backend': backend,
        }
        event = MessageDeliveryStatusEvent(
            delivery_data=delivery_data,
            tenant_uuid=tenant_uuid,
            user_uuids=user_uuids,
            room_uuid=room_uuid,
            message_uuid=message_uuid,
        )
        await self._publish(event)

    async def _publish(self, event: ServiceEvent) -> None:
        try:
            await asyncio.to_thread(self._bus.publish, event)
        except Exception:
            logger.exception('Failed to publish bus event %s', event.name)
