# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock

from wazo_chatd.database.async_helpers import _current_session
from wazo_chatd.database.models import RoomUser
from wazo_chatd.database.queries.async_.room import AsyncRoomDAO


def _make_room_user(
    uuid: str = 'user-1',
    tenant_uuid: str = 'tenant-1',
    wazo_uuid: str = 'wazo-1',
    identity: str | None = None,
) -> RoomUser:
    return RoomUser(
        uuid=uuid,
        tenant_uuid=tenant_uuid,
        wazo_uuid=wazo_uuid,
        identity=identity,
    )


class TestAsyncAddMessageMeta(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = AsyncMock()
        self.session.add = Mock()
        self.token = _current_session.set(self.session)
        self.dao = AsyncRoomDAO()

    def tearDown(self) -> None:
        _current_session.reset(self.token)

    async def test_adds_meta_and_record_then_flushes(self) -> None:
        meta = Mock()
        record = Mock()

        await self.dao.add_message_meta(meta, record)

        assert self.session.add.call_count == 2
        self.session.add.assert_any_call(meta)
        self.session.add.assert_any_call(record)
        self.session.flush.assert_awaited_once()


class TestAsyncCheckDuplicateIdempotencyKey(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = AsyncMock()
        self.token = _current_session.set(self.session)
        self.dao = AsyncRoomDAO()

    def tearDown(self) -> None:
        _current_session.reset(self.token)

    async def test_returns_true_when_key_exists(self) -> None:
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = 'some-uuid'
        self.session.execute.return_value = result_mock

        result = await self.dao.check_duplicate_idempotency_key('existing-key')

        assert result is True
        self.session.execute.assert_awaited_once()

    async def test_returns_false_when_key_not_found(self) -> None:
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = None
        self.session.execute.return_value = result_mock

        result = await self.dao.check_duplicate_idempotency_key('new-key')

        assert result is False


class TestAsyncListPendingExternalIds(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = AsyncMock()
        self.token = _current_session.set(self.session)
        self.dao = AsyncRoomDAO()

    def tearDown(self) -> None:
        _current_session.reset(self.token)

    async def test_returns_external_ids(self) -> None:
        scalars = Mock()
        scalars.all.return_value = ['sid-1', 'sid-2']
        result_mock = Mock()
        result_mock.scalars.return_value = scalars
        self.session.execute.return_value = result_mock

        result = await self.dao.list_pending_external_ids(
            tenant_uuid='tenant-1', backend='twilio'
        )

        assert result == ['sid-1', 'sid-2']
        self.session.execute.assert_awaited_once()

    async def test_returns_empty_when_no_pending(self) -> None:
        scalars = Mock()
        scalars.all.return_value = []
        result_mock = Mock()
        result_mock.scalars.return_value = scalars
        self.session.execute.return_value = result_mock

        result = await self.dao.list_pending_external_ids(
            tenant_uuid='tenant-1', backend='twilio'
        )

        assert result == []


class TestAsyncFindOrCreateRoom(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = AsyncMock()
        self.session.add = Mock()
        self.token = _current_session.set(self.session)
        self.dao = AsyncRoomDAO()

    def tearDown(self) -> None:
        _current_session.reset(self.token)

    async def test_returns_existing_room(self) -> None:
        existing_room = Mock()
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = existing_room
        self.session.execute.return_value = result_mock

        participants = [
            _make_room_user('user-1'),
            _make_room_user('ext-1', identity='+15559876'),
        ]

        room = await self.dao.find_or_create_room(
            tenant_uuid='tenant-1',
            participants=participants,
        )

        assert room is existing_room
        self.session.add.assert_not_called()

    async def test_creates_room_when_not_found(self) -> None:
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = None
        self.session.execute.return_value = result_mock

        participants = [
            _make_room_user('user-1'),
            _make_room_user('ext-1', identity='+15559876'),
        ]

        room = await self.dao.find_or_create_room(
            tenant_uuid='tenant-1',
            participants=participants,
        )

        self.session.add.assert_called_once()
        self.session.flush.assert_awaited_once()
        assert room is not None
        assert len(room.users) == 2

    async def test_creates_room_with_multiple_participants(self) -> None:
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = None
        self.session.execute.return_value = result_mock

        participants = [
            _make_room_user('user-1'),
            _make_room_user('user-2'),
            _make_room_user('ext-1', identity='+15559876'),
        ]

        room = await self.dao.find_or_create_room(
            tenant_uuid='tenant-1',
            participants=participants,
        )

        assert len(room.users) == 3
