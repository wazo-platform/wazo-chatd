# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy import text

from ...exceptions import UnknownRoomException
from ..helpers import get_dao_session
from ..models import Room, RoomUser, RoomMessage


class RoomDAO:

    @property
    def session(self):
        return get_dao_session()

    def create(self, room):
        self.session.add(room)
        self.session.flush()
        return room

    def get(self, tenant_uuids, room_uuid):
        query = self.session.query(Room).filter(
            Room.tenant_uuid.in_(tenant_uuids),
            Room.uuid == str(room_uuid),
        )
        room = query.first()
        if not room:
            raise UnknownRoomException(room_uuid)
        return room

    def list_(self, tenant_uuids, **filter_parameters):
        return self._list_query(tenant_uuids, **filter_parameters).all()

    def count(self, tenant_uuids, **filter_parameters):
        return self._list_query(tenant_uuids, **filter_parameters).count()

    def _list_query(self, tenant_uuids=None, user_uuid=None):
        query = self.session.query(Room)

        if user_uuid:
            query = query.join(RoomUser).filter(RoomUser.uuid == str(user_uuid))

        if tenant_uuids is None:
            return query

        if not tenant_uuids:
            return query.filter(text('false'))

        return query.filter(Room.tenant_uuid.in_(tenant_uuids))

    def add_message(self, room, message):
        room.messages.append(message)
        self.session.flush()

    def list_messages(self, room, limit=None, **filtered_parameters):
        query = self._list_messages_query(room.uuid, **filtered_parameters)
        if limit:
            query = query.limit(limit)
        return query.all()

    def count_messages(self, room, filtered=False, **filtered_parameters):
        filtered_parameters.pop('limit', None)
        query = self._list_messages_query(room.uuid, **filtered_parameters)
        return query.count()

    def _list_messages_query(self, room_uuid, filtered=None, order='created_at', direction='desc'):
        query = self.session.query(RoomMessage).filter(RoomMessage.room_uuid == room_uuid)
        if not filtered:
            pass

        order_column = getattr(RoomMessage, order)
        if direction == 'desc':
            order_column = order_column.desc()
        else:
            order_column = order_column.asc()

        query = query.order_by(order_column)

        return query

    def list_user_messages(self, tenant_uuid, user_uuid, limit=None, **filtered_parameters):
        query = self._list_user_messages_query(tenant_uuid, user_uuid, **filtered_parameters)
        if limit:
            query = query.limit(limit)
        return query.all()

    def count_user_messages(self, tenant_uuid, user_uuid, filtered=False, **filtered_parameters):
        filtered_parameters.pop('limit', None)
        query = self._list_user_messages_query(tenant_uuid, user_uuid, filtered, **filtered_parameters)
        return query.count()

    def _list_user_messages_query(self, tenant_uuid, user_uuid, filtered=None,
                                  search=None, order='created_at', direction='desc'):
        query = (
            self.session.query(RoomMessage)
            .join(Room)
            .join(RoomUser)
            .filter(RoomUser.tenant_uuid == tenant_uuid)
            .filter(RoomUser.uuid == user_uuid)
        )

        order_column = getattr(RoomMessage, order)
        if direction == 'desc':
            order_column = order_column.desc()
        else:
            order_column = order_column.asc()
        query = query.order_by(order_column)

        if filtered is False:
            return query

        if search:
            words = [word for word in search.split(' ') if word]
            pattern = '%{}%'.format('%'.join(words))
            query = query.filter(RoomMessage.content.ilike(pattern))

        return query
