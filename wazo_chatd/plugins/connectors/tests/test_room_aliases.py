# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from typing import ClassVar
from unittest.mock import Mock

from wazo_chatd.plugins.connectors.services import ConnectorService


class _SmsConnector:
    backend: ClassVar[str] = 'twilio'
    supported_types: ClassVar[tuple[str, ...]] = ('sms', 'mms')

    def normalize_identity(self, raw_identity: str) -> str:
        if raw_identity.startswith('+'):
            return raw_identity
        raise ValueError(f'Not a phone number: {raw_identity}')


def _make_room_user(
    uuid: str = 'user-uuid',
    identity: str | None = None,
) -> Mock:
    user = Mock()
    user.uuid = uuid
    user.identity = identity
    return user


def _make_room(users: list[Mock] | None = None) -> Mock:
    room = Mock()
    room.uuid = 'room-uuid'
    room.tenant_uuid = 'tenant-uuid'
    room.users = users or []
    return room


def _build_service(
    room: Mock | None = None,
    types_by_user: dict[str, list[str]] | None = None,
    identity_bound: dict[str, bool] | None = None,
    sender_aliases: list[Mock] | None = None,
) -> ConnectorService:
    from wazo_chatd.plugins.connectors.registry import ConnectorRegistry

    dao = Mock()
    if room is not None:
        dao.room.get.return_value = room

    types_map = types_by_user or {}
    dao.user_alias.list_types_by_user.side_effect = lambda uid: types_map.get(uid, [])

    bound_map = identity_bound or {}
    dao.user_alias.is_identity_bound.side_effect = lambda ident: bound_map.get(
        ident, False
    )

    dao.user_alias.list_by_user_and_types.return_value = sender_aliases or []

    registry = ConnectorRegistry()
    registry.register_backend(_SmsConnector)  # type: ignore[arg-type]

    return ConnectorService(dao, registry)


SENDER_UUID = 'sender-uuid'


class TestListRoomAliases(unittest.TestCase):
    def test_truly_external_participant_returns_sender_aliases(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        external = _make_room_user(uuid='ext-uuid', identity='+15559876')
        room = _make_room(users=[sender, external])

        alias = Mock()
        service = _build_service(
            room=room,
            identity_bound={'+15559876': False},
            sender_aliases=[alias],
        )

        result = service.list_room_aliases(['tenant-uuid'], 'room-uuid', SENDER_UUID)

        assert result == [alias]

    def test_wazo_user_with_sms_alias_returns_sender_aliases(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        recipient = _make_room_user(uuid='recipient-uuid')
        room = _make_room(users=[sender, recipient])

        alias = Mock()
        service = _build_service(
            room=room,
            types_by_user={'recipient-uuid': ['sms']},
            sender_aliases=[alias],
        )

        result = service.list_room_aliases(['tenant-uuid'], 'room-uuid', SENDER_UUID)

        assert result == [alias]

    def test_wazo_user_with_identity_bound_to_alias(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        recipient = _make_room_user(uuid='recipient-uuid', identity='+15559876')
        room = _make_room(users=[sender, recipient])

        alias = Mock()
        service = _build_service(
            room=room,
            identity_bound={'+15559876': True},
            types_by_user={'recipient-uuid': ['sms']},
            sender_aliases=[alias],
        )

        result = service.list_room_aliases(['tenant-uuid'], 'room-uuid', SENDER_UUID)

        assert result == [alias]

    def test_internal_only_room_returns_empty(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        other = _make_room_user(uuid='other-uuid')
        room = _make_room(users=[sender, other])

        service = _build_service(
            room=room,
            types_by_user={'other-uuid': []},
        )

        result = service.list_room_aliases(['tenant-uuid'], 'room-uuid', SENDER_UUID)

        assert result == []

    def test_multiple_participants_intersects_reachable_types(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        user_a = _make_room_user(uuid='user-a')
        user_b = _make_room_user(uuid='user-b')
        room = _make_room(users=[sender, user_a, user_b])

        alias = Mock()
        service = _build_service(
            room=room,
            types_by_user={
                'user-a': ['sms', 'whatsapp'],
                'user-b': ['sms'],
            },
            sender_aliases=[alias],
        )

        result = service.list_room_aliases(['tenant-uuid'], 'room-uuid', SENDER_UUID)

        assert result == [alias]
        service._dao.user_alias.list_by_user_and_types.assert_called_once_with(
            SENDER_UUID, ['sms']
        )

    def test_sender_has_no_matching_aliases_returns_empty(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        external = _make_room_user(uuid='ext-uuid', identity='+15559876')
        room = _make_room(users=[sender, external])

        service = _build_service(
            room=room,
            identity_bound={'+15559876': False},
            sender_aliases=[],
        )

        result = service.list_room_aliases(['tenant-uuid'], 'room-uuid', SENDER_UUID)

        assert result == []

    def test_user_not_in_room_raises(self) -> None:
        other_a = _make_room_user(uuid='other-a')
        other_b = _make_room_user(uuid='other-b')
        room = _make_room(users=[other_a, other_b])

        service = _build_service(room=room)

        from wazo_chatd.exceptions import UnknownRoomException

        with self.assertRaises(UnknownRoomException):
            service.list_room_aliases(['tenant-uuid'], 'room-uuid', SENDER_UUID)
