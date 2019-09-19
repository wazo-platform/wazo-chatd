# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later


class RoomService:
    def __init__(self, wazo_uuid, dao, notifier):
        self._dao = dao
        self._notifier = notifier
        self._wazo_uuid = wazo_uuid

    def create(self, room):
        self._set_default_room_values(room)
        self._dao.room.create(room)
        self._notifier.created(room)
        return room

    def _set_default_room_values(self, room):
        for user in room.users:
            if user.tenant_uuid is None:
                user.tenant_uuid = room.tenant_uuid
            if user.wazo_uuid is None:
                user.wazo_uuid = self._wazo_uuid

    def list_(self, tenant_uuids, **filter_parameters):
        return self._dao.room.list_(tenant_uuids, **filter_parameters)

    def count(self, tenant_uuids, **filter_parameters):
        return self._dao.room.count(tenant_uuids, **filter_parameters)

    def get(self, tenant_uuids, room_uuid):
        return self._dao.room.get(tenant_uuids, room_uuid)

    def create_message(self, room, message):
        self._set_default_message_values(message)
        self._dao.room.add_message(room, message)
        self._notifier.message_created(room, message)
        return message

    def _set_default_message_values(self, message):
        message.wazo_uuid = self._wazo_uuid

    def list_messages(self, room, **filter_parameters):
        return self._dao.room.list_messages(room, **filter_parameters)

    def count_messages(self, room, **filter_parameters):
        return self._dao.room.count_messages(room, **filter_parameters)

    def list_user_messages(self, tenant_uuid, user_uuid, **filter_parameters):
        return self._dao.room.list_user_messages(
            tenant_uuid, user_uuid, **filter_parameters
        )

    def count_user_messages(self, tenant_uuid, user_uuid, **filter_parameters):
        return self._dao.room.count_user_messages(
            tenant_uuid, user_uuid, **filter_parameters
        )

    def list_latest_user_messages(self, tenant_uuid, user_uuid, **filter_parameters):
        return self._dao.room.list_latest_user_messages(
            tenant_uuid, user_uuid, **filter_parameters
        )

    def count_latest_user_messages(self, tenant_uuid, user_uuid, **filter_parameters):
        return self._dao.room.count_latest_user_messages(
            tenant_uuid, user_uuid, **filter_parameters
        )
