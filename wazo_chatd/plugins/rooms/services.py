# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later


class RoomService:

    def __init__(self, wazo_uuid, dao, notifier):
        self._dao = dao
        self._notifier = notifier
        self._wazo_uuid = wazo_uuid

    def create(self, room):
        self._set_default_values(room)
        self._dao.room.create(room)
        self._notifier.created(room)
        return room

    def _set_default_values(self, room):
        for user in room.users:
            if user.tenant_uuid is None:
                user.tenant_uuid = room.tenant_uuid
            if user.wazo_uuid is None:
                user.wazo_uuid = self._wazo_uuid

    def list_(self, tenant_uuids, **filter_parameters):
        return self._dao.room.list_(tenant_uuids, **filter_parameters)

    def count(self, tenant_uuids, **filter_parameters):
        return self._dao.room.count(tenant_uuids, **filter_parameters)
