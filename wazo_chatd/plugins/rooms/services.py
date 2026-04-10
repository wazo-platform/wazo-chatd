# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from wazo_chatd.plugin_helpers.dependencies import MessageContext
from wazo_chatd.plugin_helpers.hooks import Hooks

if TYPE_CHECKING:
    from wazo_chatd.database.models import Room, RoomMessage
    from wazo_chatd.database.queries import DAO
    from wazo_chatd.plugins.rooms.notifier import RoomNotifier


class RoomService:
    def __init__(
        self,
        wazo_uuid: str,
        dao: DAO,
        notifier: RoomNotifier,
        hooks: Hooks,
    ) -> None:
        self._dao = dao
        self._notifier = notifier
        self._wazo_uuid = wazo_uuid
        self._hooks = hooks

    def create(self, room):
        self._set_default_room_values(room)
        self._hooks.dispatch('before_room_creation', room, allow_raise=True)
        self._dao.room.create(room)
        self._notifier.created(room)
        return room

    def _set_default_room_values(self, room):
        for user in room.users:
            if user.tenant_uuid is None:
                user.tenant_uuid = room.tenant_uuid
            if user.wazo_uuid is None:
                user.wazo_uuid = self._wazo_uuid

    def has_delivery_pipeline(self) -> bool:
        return self._hooks.has_subscribers('before_message_creation')

    def list_(self, tenant_uuids, **filter_parameters):
        return self._dao.room.list_(tenant_uuids, **filter_parameters)

    def count(self, tenant_uuids, **filter_parameters):
        return self._dao.room.count(tenant_uuids, **filter_parameters)

    def get(self, tenant_uuids, room_uuid):
        return self._dao.room.get(tenant_uuids, room_uuid)

    def create_message(
        self,
        room: Room,
        message: RoomMessage,
        sender_identity_uuid: UUID | None = None,
    ) -> RoomMessage:
        self._set_default_message_values(message)
        context = MessageContext(
            room, message, sender_identity_uuid=sender_identity_uuid
        )
        self._hooks.dispatch('before_message_creation', context, allow_raise=True)
        self._dao.room.add_message(room, message)
        self._notifier.message_created(room, message)
        return message

    def _set_default_message_values(self, message):
        message.wazo_uuid = self._wazo_uuid

    def list_messages(self, room, viewer_uuid: str | None = None, **filter_parameters):
        return self._dao.room.list_messages(
            room, viewer_uuid=viewer_uuid, **filter_parameters
        )

    def count_messages(self, room, viewer_uuid: str | None = None, **filter_parameters):
        return self._dao.room.count_messages(
            room, viewer_uuid=viewer_uuid, **filter_parameters
        )

    def list_user_messages(self, tenant_uuid, user_uuid, **filter_parameters):
        return self._dao.room.list_user_messages(
            tenant_uuid, user_uuid, **filter_parameters
        )

    def count_user_messages(self, tenant_uuid, user_uuid, **filter_parameters):
        return self._dao.room.count_user_messages(
            tenant_uuid, user_uuid, **filter_parameters
        )
