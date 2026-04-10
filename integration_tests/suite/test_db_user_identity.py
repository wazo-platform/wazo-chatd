# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

from wazo_chatd.database.models import Room, RoomUser, UserIdentity

from .helpers import fixtures
from .helpers.base import TOKEN_TENANT_UUID as TENANT_1
from .helpers.base import WAZO_UUID, DBIntegrationTest, use_asset

USER_UUID_1 = uuid.uuid4()
USER_UUID_2 = uuid.uuid4()


@use_asset('database')
class TestUserIdentity(DBIntegrationTest):
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='twilio',
        type_='sms',
        identity='+15551234567',
    )
    def test_create_identity(self, identity, user):
        result = (
            self._session.query(UserIdentity)
            .filter(UserIdentity.identity == '+15551234567')
            .first()
        )

        assert result is not None
        assert result.user_uuid == USER_UUID_1
        assert result.backend == 'twilio'

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='twilio',
        type_='sms',
        identity='+15551111111',
    )
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='vonage',
        type_='sms',
        identity='+15552222222',
    )
    def test_user_multiple_identities(
        self,
        identity_2,
        identity_1,
        user,
    ):
        results = (
            self._session.query(UserIdentity)
            .filter(UserIdentity.user_uuid == USER_UUID_1)
            .all()
        )

        assert len(results) == 2


@use_asset('database')
class TestRoomUserIdentity(DBIntegrationTest):
    @fixtures.db.room(
        users=[
            {'uuid': USER_UUID_1},
            {'uuid': USER_UUID_2, 'identity': '+15559876543'},
        ],
    )
    def test_room_with_external_participant(self, room):
        internal_user = next(u for u in room.users if u.uuid == USER_UUID_1)
        external_user = next(u for u in room.users if u.uuid == USER_UUID_2)

        assert internal_user.identity is None
        assert external_user.identity == '+15559876543'

    @fixtures.db.room(
        users=[
            {'uuid': USER_UUID_1},
            {'uuid': USER_UUID_2},
        ],
    )
    def test_room_all_internal(self, room):
        for user in room.users:
            assert user.identity is None

    def test_query_by_identity(self):
        ext_uuid = uuid.uuid4()
        room = Room(tenant_uuid=TENANT_1)
        room.users = [
            RoomUser(
                uuid=ext_uuid,
                tenant_uuid=TENANT_1,
                wazo_uuid=WAZO_UUID,
                identity='+15559999999',
            ),
        ]
        self._session.add(room)
        self._session.flush()

        results = (
            self._session.query(RoomUser)
            .filter(RoomUser.identity == '+15559999999')
            .all()
        )

        assert len(results) == 1
        assert results[0].uuid == ext_uuid

        # cleanup
        self._session.query(Room).filter(Room.uuid == room.uuid).delete()
        self._session.commit()
