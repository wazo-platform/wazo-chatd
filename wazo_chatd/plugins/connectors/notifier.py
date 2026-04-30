# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast

from wazo_bus.resources.chatd.events import (
    MessageDeliveryStatusEvent,
    UserIdentityCreatedEvent,
    UserIdentityDeletedEvent,
    UserIdentityUpdatedEvent,
    UserRoomCreatedEvent,
    UserRoomMessageCreatedEvent,
)
from wazo_bus.resources.chatd.types import DeliveryStatusDict, MessageDict
from wazo_bus.resources.common.event import ServiceEvent

from wazo_chatd.database.delivery import DeliveryStatus
from wazo_chatd.database.models import (
    DeliveryRecord,
    MessageDelivery,
    Room,
    RoomMessage,
    UserIdentity,
)
from wazo_chatd.plugins.connectors.schemas import UserIdentitySchema
from wazo_chatd.plugins.rooms.schemas import MessageSchema, RoomSchema

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

    async def room_created(self, room: Room) -> None:
        room_data = RoomSchema().dump(room)
        for user in room.users:
            event = UserRoomCreatedEvent(
                room_data, str(room.tenant_uuid), str(user.uuid)
            )
            await self._publish(event)

    async def message_created(self, room: Room, message: RoomMessage) -> None:
        message_data = self._build_message_payload(message)
        for user in room.users:
            event = UserRoomMessageCreatedEvent(
                message_data, room.uuid, room.tenant_uuid, user.uuid
            )
            await self._publish(event)

    async def delivery_status_updated(
        self,
        delivery: MessageDelivery,
        record: DeliveryRecord,
    ) -> None:
        meta = delivery.meta
        room = meta.message.room
        delivery_data: DeliveryStatusDict = {
            'message_uuid': str(meta.message_uuid),
            'recipient_identity': str(delivery.recipient_identity),
            'status': str(record.status),
            'timestamp': record.timestamp.isoformat(),
            'backend': str(meta.backend),
        }
        event = MessageDeliveryStatusEvent(
            delivery_data=delivery_data,
            room_uuid=str(room.uuid),
            message_uuid=str(meta.message_uuid),
            tenant_uuid=str(room.tenant_uuid),
            user_uuid=str(meta.message.user_uuid),
        )
        await self._publish(event)

        if record.status == DeliveryStatus.DELIVERED.value:
            await self._notify_message_delivered(meta.message, room)

    @staticmethod
    def _build_message_payload(message: RoomMessage) -> MessageDict:
        # Reuse the sync schema so both notifier paths publish the same
        # shape: handles meta=None via the _default_delivery post_dump
        # and includes the recipients list.
        return cast(MessageDict, MessageSchema().dump(message))

    async def _notify_message_delivered(self, message: RoomMessage, room: Room) -> None:
        sender_uuid = str(message.user_uuid)
        recipients = [
            u for u in room.users if not u.identity and str(u.uuid) != sender_uuid
        ]
        if not recipients:
            return

        message_data = self._build_message_payload(message)
        for user in recipients:
            event = UserRoomMessageCreatedEvent(
                message_data, room.uuid, room.tenant_uuid, user.uuid
            )
            await self._publish(event)

    async def _publish(self, event: ServiceEvent) -> None:
        try:
            await asyncio.to_thread(self._bus.publish, event)
        except Exception:
            logger.exception('Failed to publish bus event %s', event.name)
