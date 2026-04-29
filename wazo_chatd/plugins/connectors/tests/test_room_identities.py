# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
import uuid
from typing import ClassVar
from unittest.mock import Mock

import pytest

from wazo_chatd.plugins.connectors.exceptions import (
    InvalidIdentityException,
    UnreachableParticipantException,
)
from wazo_chatd.plugins.connectors.services import ConnectorService


class _SmsConnector:
    backend: ClassVar[str] = 'sms_backend'
    supported_types: ClassVar[tuple[str, ...]] = ('sms', 'mms')

    @classmethod
    def normalize_identity(cls, raw_identity: str) -> str:
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
    sender_identities: list[Mock] | None = None,
) -> ConnectorService:
    from wazo_chatd.plugins.connectors.registry import ConnectorRegistry

    dao = Mock()
    if room is not None:
        dao.room.get.return_value = room

    types_map = types_by_user or {}
    dao.user_identity.list_types_by_users.side_effect = lambda uids: {
        uid: set(types_map.get(uid, [])) for uid in uids
    }

    bound_map = identity_bound or {}
    dao.user_identity.is_identity_bound.side_effect = lambda ident: bound_map.get(
        ident, False
    )
    dao.user_identity.list_bound_identities.side_effect = lambda idents: {
        ident for ident in idents if bound_map.get(ident, False)
    }

    dao.user_identity.list_by_user.return_value = sender_identities or []

    registry = ConnectorRegistry()
    registry.register_backend(_SmsConnector)  # type: ignore[arg-type]

    return ConnectorService(dao, registry, Mock(), Mock())


SENDER_UUID = 'sender-uuid'


class TestListRoomIdentities(unittest.TestCase):
    def test_truly_external_participant_returns_sender_identities(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        external = _make_room_user(uuid='ext-uuid', identity='+15559876')
        room = _make_room(users=[sender, external])

        identity_mock = Mock()
        service = _build_service(
            room=room,
            identity_bound={'+15559876': False},
            sender_identities=[identity_mock],
        )

        result = service.list_room_identities(['tenant-uuid'], 'room-uuid', SENDER_UUID)

        assert result == [identity_mock]

    def test_wazo_user_with_sms_identity_returns_sender_identities(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        recipient = _make_room_user(uuid='recipient-uuid')
        room = _make_room(users=[sender, recipient])

        identity_mock = Mock()
        service = _build_service(
            room=room,
            types_by_user={'recipient-uuid': ['sms']},
            sender_identities=[identity_mock],
        )

        result = service.list_room_identities(['tenant-uuid'], 'room-uuid', SENDER_UUID)

        assert result == [identity_mock]

    def test_wazo_user_with_identity_bound(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        recipient = _make_room_user(uuid='recipient-uuid', identity='+15559876')
        room = _make_room(users=[sender, recipient])

        identity_mock = Mock()
        service = _build_service(
            room=room,
            identity_bound={'+15559876': True},
            types_by_user={'recipient-uuid': ['sms']},
            sender_identities=[identity_mock],
        )

        result = service.list_room_identities(['tenant-uuid'], 'room-uuid', SENDER_UUID)

        assert result == [identity_mock]

    def test_internal_only_room_returns_empty(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        other = _make_room_user(uuid='other-uuid')
        room = _make_room(users=[sender, other])

        service = _build_service(
            room=room,
            types_by_user={'other-uuid': []},
        )

        result = service.list_room_identities(['tenant-uuid'], 'room-uuid', SENDER_UUID)

        assert result == []

    def test_multiple_participants_returns_empty(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        user_a = _make_room_user(uuid='user-a')
        user_b = _make_room_user(uuid='user-b')
        room = _make_room(users=[sender, user_a, user_b])

        service = _build_service(
            room=room,
            types_by_user={'user-a': ['sms'], 'user-b': ['sms']},
            sender_identities=[Mock()],
        )

        result = service.list_room_identities(['tenant-uuid'], 'room-uuid', SENDER_UUID)

        assert result == []

    def test_sender_has_no_matching_identities_returns_empty(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        external = _make_room_user(uuid='ext-uuid', identity='+15559876')
        room = _make_room(users=[sender, external])

        service = _build_service(
            room=room,
            identity_bound={'+15559876': False},
            sender_identities=[],
        )

        result = service.list_room_identities(['tenant-uuid'], 'room-uuid', SENDER_UUID)

        assert result == []

    def test_user_not_in_room_raises(self) -> None:
        other_a = _make_room_user(uuid='other-a')
        other_b = _make_room_user(uuid='other-b')
        room = _make_room(users=[other_a, other_b])

        service = _build_service(room=room)

        from wazo_chatd.exceptions import UnknownRoomException

        with self.assertRaises(UnknownRoomException):
            service.list_room_identities(['tenant-uuid'], 'room-uuid', SENDER_UUID)


def _make_identity(backend: str = 'sms_backend', type_: str = 'sms') -> Mock:
    identity_mock = Mock()
    identity_mock.backend = backend
    identity_mock.type_ = type_
    return identity_mock


class TestValidateIdentityReachability(unittest.TestCase):
    def test_both_internal_users_share_type_passes(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        recipient = _make_room_user(uuid='recipient-uuid')
        room = _make_room(users=[sender, recipient])

        identity = _make_identity('sms_backend')
        service = _build_service(
            room=room,
            types_by_user={'recipient-uuid': ['sms']},
        )
        service._dao.user_identity.find.return_value = identity

        service.validate_identity_reachability(room, SENDER_UUID, uuid.uuid4())

    def test_recipient_missing_type_raises(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        recipient = _make_room_user(uuid='recipient-uuid')
        room = _make_room(users=[sender, recipient])

        identity = _make_identity('sms_backend')
        service = _build_service(
            room=room,
            types_by_user={'recipient-uuid': []},
        )
        service._dao.user_identity.find.return_value = identity

        with pytest.raises(UnreachableParticipantException):
            service.validate_identity_reachability(room, SENDER_UUID, uuid.uuid4())

    def test_external_participant_reachable_passes(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        external = _make_room_user(uuid='ext-uuid', identity='+15559876')
        room = _make_room(users=[sender, external])

        identity = _make_identity('sms_backend')
        service = _build_service(
            room=room,
            identity_bound={'+15559876': False},
        )
        service._dao.user_identity.find.return_value = identity

        service.validate_identity_reachability(room, SENDER_UUID, uuid.uuid4())

    def test_find_filters_by_user_uuid(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        recipient = _make_room_user(uuid='recipient-uuid')
        room = _make_room(users=[sender, recipient])

        identity = _make_identity()
        service = _build_service(
            room=room,
            types_by_user={'recipient-uuid': ['sms']},
        )
        service._dao.user_identity.find.return_value = identity

        identity_uuid = uuid.uuid4()
        service.validate_identity_reachability(room, SENDER_UUID, identity_uuid)

        service._dao.user_identity.find.assert_called_once_with(
            identity_uuid, user_uuid=SENDER_UUID
        )

    def test_invalid_identity_uuid_raises(self) -> None:
        sender = _make_room_user(uuid=SENDER_UUID)
        recipient = _make_room_user(uuid='recipient-uuid')
        room = _make_room(users=[sender, recipient])

        service = _build_service(room=room)
        service._dao.user_identity.find.return_value = None

        with pytest.raises(InvalidIdentityException):
            service.validate_identity_reachability(room, SENDER_UUID, uuid.uuid4())


class TestValidateRoomReachability(unittest.TestCase):
    def test_internal_only_room_skips_validation(self) -> None:
        user_a = _make_room_user(uuid='user-a')
        user_b = _make_room_user(uuid='user-b')
        room = _make_room(users=[user_a, user_b])

        service = _build_service(room=room)

        service.validate_room_reachability(room)

    def test_external_participant_reachable_passes(self) -> None:
        user_a = _make_room_user(uuid='user-a')
        external = _make_room_user(uuid='ext-uuid', identity='+15559876')
        room = _make_room(users=[user_a, external])

        service = _build_service(
            room=room,
            identity_bound={'+15559876': False},
            types_by_user={'user-a': ['sms']},
        )
        service._dao.user_identity.list_bound_identities.return_value = set()

        service.validate_room_reachability(room)

    def test_external_participant_unreachable_raises(self) -> None:
        user_a = _make_room_user(uuid='user-a')
        external = _make_room_user(uuid='ext-uuid', identity='not-reachable')
        room = _make_room(users=[user_a, external])

        service = _build_service(room=room)
        service._dao.user_identity.list_bound_identities.return_value = set()

        with pytest.raises(UnreachableParticipantException):
            service.validate_room_reachability(room)

    def test_group_room_with_external_is_rejected(self) -> None:
        user_a = _make_room_user(uuid='user-a')
        user_b = _make_room_user(uuid='user-b')
        external = _make_room_user(uuid='ext-uuid', identity='+15559876')
        room = _make_room(users=[user_a, user_b, external])

        service = _build_service(
            room=room,
            types_by_user={'user-a': ['sms'], 'user-b': ['sms']},
        )
        service._dao.user_identity.list_bound_identities.return_value = set()

        with pytest.raises(UnreachableParticipantException):
            service.validate_room_reachability(room)
