# Copyright 2019-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy import and_, distinct, text
from sqlalchemy.dialects.postgresql import array_agg
from sqlalchemy.orm import Query, aliased
from sqlalchemy.sql.functions import ReturnTypeFromArgs

from wazo_chatd.database.helpers import get_query_main_entity

from ...exceptions import UnknownRoomException
from ..models import Room, RoomMessage, RoomUser


class unaccent(ReturnTypeFromArgs):
    inherit_cache = True


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

    def _list_query(self, tenant_uuids=None, user_uuids=None, exact_user_uuids=False):
        query = self.session.query(Room)
        if user_uuids:
            matcher = array_agg(distinct(RoomUser.uuid)).contains(user_uuids)
            if exact_user_uuids:
                matcher = and_(
                    matcher,
                    array_agg(distinct(RoomUser.uuid)).contained_by(  # type: ignore[attr-defined]
                        user_uuids
                    ),
                )

            sub_query = (
                self.session.query(RoomUser.room_uuid)
                .group_by(RoomUser.room_uuid)
                .having(matcher)
            ).subquery()
            query = query.filter(Room.uuid.in_(sub_query.select()))

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
        order_column = getattr(get_query_main_entity(query), order)
        order_column = order_column.asc() if direction == 'asc' else order_column.desc()
        query = query.order_by(order_column)

        if limit is not None:
            query = query.limit(limit)
        if offset is not None:
            query = query.offset(offset)

        return query

    def _list_filter(
        self,
        query: Query,
        search=None,
        from_date=None,
        distinct=None,
        **ignored,
    ):
        if distinct is not None:
            distinct_field = getattr(RoomMessage, distinct)
            distinct_query = (
                query.distinct(distinct_field)
                .order_by(distinct_field, RoomMessage.created_at.desc())
                .subquery()
            )
            distinct_entity = aliased(
                RoomMessage,
                distinct_query,
                name='distinct_messages',
            )
            query = self.session.query(distinct_entity)

        if search is not None:
            words = [word for word in search.split(' ') if word]
            pattern = f'%{"%".join(words)}%'
            query = query.filter(
                unaccent(get_query_main_entity(query).content).ilike(pattern)
            )

        if from_date is not None:
            query = query.filter(get_query_main_entity(query).created_at >= from_date)

        return query
