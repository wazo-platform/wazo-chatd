# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock

from wazo_chatd.database.models import RoomUser
from wazo_chatd.database.queries.async_.room import (
    add_message_meta,
    check_duplicate_idempotency_key,
    find_or_create_room,
)


class TestAsyncAddMessageMeta(unittest.IsolatedAsyncioTestCase):
    async def test_adds_meta_and_record_then_flushes(self) -> None:
        session = AsyncMock()
        session.add = Mock()
        meta = Mock()
        record = Mock()

        await add_message_meta(session, meta, record)

        assert session.add.call_count == 2
        session.add.assert_any_call(meta)
        session.add.assert_any_call(record)
        session.flush.assert_awaited_once()


class TestAsyncCheckDuplicateIdempotencyKey(unittest.IsolatedAsyncioTestCase):
    async def test_returns_true_when_key_exists(self) -> None:
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = 'some-uuid'
        session = AsyncMock()
        session.execute.return_value = result_mock

        result = await check_duplicate_idempotency_key(session, 'existing-key')

        assert result is True
        session.execute.assert_awaited_once()

    async def test_returns_false_when_key_not_found(self) -> None:
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = None
        session = AsyncMock()
        session.execute.return_value = result_mock

        result = await check_duplicate_idempotency_key(session, 'new-key')

        assert result is False


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


class TestAsyncFindOrCreateRoom(unittest.IsolatedAsyncioTestCase):
    async def test_returns_existing_room(self) -> None:
        existing_room = Mock()
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = existing_room
        session = AsyncMock()
        session.execute.return_value = result_mock
        session.add = Mock()

        participants = [
            _make_room_user('user-1'),
            _make_room_user('ext-1', identity='+15559876'),
        ]

        room = await find_or_create_room(
            session,
            tenant_uuid='tenant-1',
            participants=participants,
        )

        assert room is existing_room
        session.add.assert_not_called()

    async def test_creates_room_when_not_found(self) -> None:
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = None
        session = AsyncMock()
        session.execute.return_value = result_mock
        session.add = Mock()

        participants = [
            _make_room_user('user-1'),
            _make_room_user('ext-1', identity='+15559876'),
        ]

        room = await find_or_create_room(
            session,
            tenant_uuid='tenant-1',
            participants=participants,
        )

        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert room is not None
        assert len(room.users) == 2

    async def test_creates_room_with_multiple_participants(self) -> None:
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = None
        session = AsyncMock()
        session.execute.return_value = result_mock
        session.add = Mock()

        participants = [
            _make_room_user('user-1'),
            _make_room_user('user-2'),
            _make_room_user('ext-1', identity='+15559876'),
        ]

        room = await find_or_create_room(
            session,
            tenant_uuid='tenant-1',
            participants=participants,
        )

        assert len(room.users) == 3
