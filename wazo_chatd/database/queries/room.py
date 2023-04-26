# Copyright 2019-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy.sql.functions import ReturnTypeFromArgs
from sqlalchemy import distinct, text
from sqlalchemy.dialects import postgresql

from ...exceptions import UnknownRoomException
from ..models import Room, RoomUser, RoomMessage


class unaccent(ReturnTypeFromArgs):
    pass


class RoomDAO:
    def __init__(self, session):
        self._session = session

    @property
    def session(self):
        return self._session()

    def create(self, room):
        self.session.add(room)
        self.session.flush()
        return room

    def get(self, tenant_uuids, room_uuid):
        query = self.session.query(Room).filter(
            Room.tenant_uuid.in_(tenant_uuids), Room.uuid == room_uuid
        )
        room = query.first()
        if not room:
            raise UnknownRoomException(room_uuid)
        return room

    def list_(self, tenant_uuids, **filter_parameters):
        return self._list_query(tenant_uuids, **filter_parameters).all()

    def count(self, tenant_uuids, **filter_parameters):
        return self._list_query(tenant_uuids, **filter_parameters).count()

    def _list_query(self, tenant_uuids=None, user_uuids=None):
        query = self.session.query(Room)

        if user_uuids:
            sub_query = (
                self.session.query(RoomUser.room_uuid)
                .group_by(RoomUser.room_uuid)
                .having(
                    postgresql.array_agg(distinct(RoomUser.uuid)).contains(user_uuids)
                )
            ).subquery()
            query = query.filter(Room.uuid.in_(sub_query))

        if tenant_uuids is None:
            return query

        if not tenant_uuids:
            return query.filter(text('false'))

        return query.filter(Room.tenant_uuid.in_(tenant_uuids))

    def add_message(self, room, message):
        room.messages.append(message)
        self.session.flush()

    def list_messages(self, room, **filter_parameters):
        query = self._build_messages_query(room.uuid)
        query = self._list_filter(query, **filter_parameters)
        query = self._paginate(query, **filter_parameters)
        return query.all()

    def count_messages(self, room, **filter_parameters):
        query = self._build_messages_query(room.uuid)
        query = self._list_filter(query, **filter_parameters)
        return query.count()

    def _build_messages_query(self, room_uuid):
        return self.session.query(RoomMessage).filter(
            RoomMessage.room_uuid == room_uuid
        )

    def list_user_messages(self, tenant_uuid, user_uuid, **filter_parameters):
        query = self._build_user_messages_query(tenant_uuid, user_uuid)
        query = self._list_filter(query, **filter_parameters)
        query = self._paginate(query, **filter_parameters)
        return query.all()

    def count_user_messages(self, tenant_uuid, user_uuid, **filter_parameters):
        query = self._build_user_messages_query(tenant_uuid, user_uuid)
        query = self._list_filter(query, **filter_parameters)
        return query.count()

    def _build_user_messages_query(self, tenant_uuid, user_uuid, *filters):
        return (
            self.session.query(RoomMessage)
            .join(Room)
            .join(RoomUser)
            .filter(RoomUser.tenant_uuid == tenant_uuid)
            .filter(RoomUser.uuid == user_uuid)
        )

    def _paginate(
        self,
        query,
        limit=None,
        offset=None,
        order='created_at',
        direction='desc',
        **ignored,
    ):
        order_column = getattr(RoomMessage, order)
        order_column = order_column.asc() if direction == 'asc' else order_column.desc()
        query = query.order_by(order_column)

        if limit is not None:
            query = query.limit(limit)
        if offset is not None:
            query = query.offset(offset)

        return query

    def _list_filter(
        self, query, search=None, from_date=None, distinct=None, **ignored
    ):
        if distinct is not None:
            distinct_field = getattr(RoomMessage, distinct)
            query = (
                query.distinct(distinct_field)
                .order_by(distinct_field, RoomMessage.created_at.desc())
                .from_self()
            )

        if search is not None:
            words = [word for word in search.split(' ') if word]
            pattern = f'%{"%".join(words)}%'
            query = query.filter(unaccent(RoomMessage.content).ilike(pattern))

        if from_date is not None:
            query = query.filter(RoomMessage.created_at >= from_date)

        return query
