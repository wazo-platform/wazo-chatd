# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
import uuid
from unittest.mock import Mock

import pytest

from wazo_chatd.plugin_helpers.dependencies import MessageContext
from wazo_chatd.plugin_helpers.hooks import Hooks
from wazo_chatd.plugins.rooms.services import RoomService

WAZO_UUID = 'test-wazo-uuid'


class TestRoomServiceCreate(unittest.TestCase):
    def setUp(self) -> None:
        self.dao = Mock()
        self.notifier = Mock()
        self.hooks = Hooks()
        self.service = RoomService(
            WAZO_UUID,
            self.dao,
            self.notifier,
            self.hooks,
        )
        self.room = Mock(
            tenant_uuid='tenant-uuid',
            users=[Mock(tenant_uuid=None, wazo_uuid=None)],
        )

    def test_create_dispatches_room_creating_before_persist(self) -> None:
        call_order: list[str] = []
        self.hooks.register('room_creating', lambda _: call_order.append('creating'))
        self.dao.room.create.side_effect = lambda *a: call_order.append('persist')

        self.service.create(self.room)

        assert call_order == ['creating', 'persist']

    def test_create_room_creating_hook_rejects(self) -> None:
        self.hooks.register(
            'room_creating', Mock(side_effect=ValueError('rejected'))
        )

        with pytest.raises(ValueError, match='rejected'):
            self.service.create(self.room)

        self.dao.room.create.assert_not_called()
        self.notifier.created.assert_not_called()


class TestRoomServiceCreateMessage(unittest.TestCase):
    def setUp(self) -> None:
        self.dao = Mock()
        self.notifier = Mock()
        self.hooks = Hooks()
        self.service = RoomService(
            WAZO_UUID,
            self.dao,
            self.notifier,
            self.hooks,
        )
        self.room = Mock()
        self.message = Mock(wazo_uuid=None)
        self.sender_alias_uuid = uuid.uuid4()

    def test_create_message_persists_and_notifies(self) -> None:
        result = self.service.create_message(self.room, self.message)

        self.dao.room.add_message.assert_called_once_with(self.room, self.message)
        self.notifier.message_created.assert_called_once_with(self.room, self.message)
        assert result is self.message
        assert self.message.wazo_uuid == WAZO_UUID

    def test_create_message_dispatches_context_to_created_hook(self) -> None:
        callback = Mock()
        self.hooks.register('room_message_created', callback)

        self.service.create_message(
            self.room, self.message, sender_alias_uuid=self.sender_alias_uuid
        )

        ctx = callback.call_args[0][0]
        assert isinstance(ctx, MessageContext)
        assert ctx.room is self.room
        assert ctx.message is self.message
        assert ctx.sender_alias_uuid == self.sender_alias_uuid

    def test_create_message_notifies_even_when_created_hook_fails(self) -> None:
        self.hooks.register('room_message_created', Mock(side_effect=RuntimeError))

        self.service.create_message(self.room, self.message)

        self.notifier.message_created.assert_called_once_with(self.room, self.message)

    def test_create_message_dispatches_creating_hook_before_persist(self) -> None:
        call_order: list[str] = []
        self.hooks.register(
            'room_message_creating', lambda _: call_order.append('creating')
        )
        self.dao.room.add_message.side_effect = lambda *a: call_order.append('persist')

        self.service.create_message(self.room, self.message)

        assert call_order == ['creating', 'persist']

    def test_create_message_creating_hook_rejects(self) -> None:
        self.hooks.register(
            'room_message_creating', Mock(side_effect=ValueError('rejected'))
        )

        with pytest.raises(ValueError, match='rejected'):
            self.service.create_message(self.room, self.message)

        self.dao.room.add_message.assert_not_called()
        self.notifier.message_created.assert_not_called()

    def test_create_message_without_sender_alias_uuid(self) -> None:
        callback = Mock()
        self.hooks.register('room_message_created', callback)

        self.service.create_message(self.room, self.message)

        ctx = callback.call_args[0][0]
        assert isinstance(ctx, MessageContext)
        assert ctx.sender_alias_uuid is None
