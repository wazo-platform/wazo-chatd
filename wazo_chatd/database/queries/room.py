# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy import text

from ...exceptions import UnknownRoomException
from ..helpers import get_dao_session
from ..models import Room


class RoomDAO:

    @property
    def session(self):
        return get_dao_session()

    def get(self, tenant_uuids, room_uuid):
        query = self.session.query(Room).filter(
            Room.tenant_uuid.in_(tenant_uuids),
            Room.uuid == str(room_uuid),
        )
        room = query.first()
        if not room:
            raise UnknownRoomException(room_uuid)
        return room

    def list_(self, tenant_uuids):
        return self._list_query(tenant_uuids).all()

    def count(self, tenant_uuids):
        return self._list_query(tenant_uuids).count()

    def _list_query(self, tenant_uuids=None):
        query = self.session.query(Room)

        if tenant_uuids is None:
            return query

        if not tenant_uuids:
            return query.filter(text('false'))

        return query.filter(Room.tenant_uuid.in_(tenant_uuids))

    def update(self, room):
        self.session.add(room)
        self.session.flush()
