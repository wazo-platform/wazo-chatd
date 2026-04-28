# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import pytest
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import HTTPError

from wazo_chatd.database.models import UserIdentity
from wazo_chatd.database.queries.user_identity import UserIdentityDAO
from wazo_chatd.exceptions import UnknownUserException, UnknownUserIdentityException
from wazo_chatd.plugin_helpers.tenant import make_uuid5
from wazo_chatd.plugins.connectors.exceptions import (
    AuthServiceUnavailableException,
    InvalidIdentityFormatException,
    UnknownBackendException,
)
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry
from wazo_chatd.plugins.connectors.services import ConnectorService

TENANT_A = 'tenant-a-uuid'
USER_UUID = 'user-uuid'
IDENTITY_UUID = 'identity-uuid'


BACKEND = 'test-backend'


def _make_identity(
    identity_uuid: str = IDENTITY_UUID,
    user_uuid: str = USER_UUID,
    tenant_uuid: str = TENANT_A,
    backend: str = BACKEND,
    identity: str = '+15551234',
) -> UserIdentity:
    obj = UserIdentity(
        user_uuid=user_uuid,
        tenant_uuid=tenant_uuid,
        backend=backend,
        identity=identity,
    )
    obj.uuid = identity_uuid  # type: ignore[assignment]
    return obj


def _mock_execute(*results: UserIdentity) -> Mock:
    scalars = Mock()
    scalars.all.return_value = list(results)
    scalars.first.return_value = results[0] if results else None

    execute_result = Mock()
    execute_result.scalars.return_value = scalars
    return execute_result


def _make_dao(execute_result: Mock) -> UserIdentityDAO:
    session = Mock()
    session.execute.return_value = execute_result
    return UserIdentityDAO(lambda: session)


class TestUserIdentityDAOCreate(unittest.TestCase):
    def test_create_adds_and_flushes(self) -> None:
        dao = _make_dao(_mock_execute())
        identity = _make_identity()

        result = dao.create(identity)

        assert result is identity
        dao.session.add.assert_called_once_with(identity)
        dao.session.flush.assert_called_once()


class TestUserIdentityDAOListByUser(unittest.TestCase):
    def test_returns_identities(self) -> None:
        identity = _make_identity()
        dao = _make_dao(_mock_execute(identity))

        result = dao.list_by_user(USER_UUID, tenant_uuids=[TENANT_A])

        assert result == [identity]

    def test_returns_empty_when_no_match(self) -> None:
        dao = _make_dao(_mock_execute())

        result = dao.list_by_user(USER_UUID, tenant_uuids=[TENANT_A])

        assert result == []


class TestUserIdentityDAOGet(unittest.TestCase):
    def test_get_returns_identity(self) -> None:
        identity = _make_identity()
        dao = _make_dao(_mock_execute(identity))

        result = dao.get([TENANT_A], IDENTITY_UUID, user_uuid=USER_UUID)

        assert result is identity

    def test_get_raises_when_not_found(self) -> None:
        dao = _make_dao(_mock_execute())

        with self.assertRaises(UnknownUserIdentityException):
            dao.get([TENANT_A], 'nonexistent')

    def test_get_without_user_uuid(self) -> None:
        identity = _make_identity()
        dao = _make_dao(_mock_execute(identity))

        result = dao.get([TENANT_A], IDENTITY_UUID)

        assert result is identity


class TestUserIdentityDAOUpdate(unittest.TestCase):
    def test_update_flushes(self) -> None:
        dao = _make_dao(_mock_execute())
        identity = _make_identity()

        dao.update(identity)

        dao.session.flush.assert_called_once()


class TestUserIdentityDAODelete(unittest.TestCase):
    def test_delete_removes_and_flushes(self) -> None:
        dao = _make_dao(_mock_execute())
        identity = _make_identity()

        dao.delete(identity)

        dao.session.delete.assert_called_once_with(identity)
        dao.session.flush.assert_called_once()


class TestUserIdentityDAOFindTenantByIdentity(unittest.TestCase):
    def _make_dao_returning(self, tenant_uuid: str | None) -> UserIdentityDAO:
        scalars = Mock()
        scalars.first.return_value = tenant_uuid
        execute_result = Mock()
        execute_result.scalars.return_value = scalars
        session = Mock()
        session.execute.return_value = execute_result
        return UserIdentityDAO(lambda: session)

    def test_returns_tenant_uuid_for_match(self) -> None:
        dao = self._make_dao_returning(TENANT_A)

        result = dao.find_tenant_by_identity('+15551234', BACKEND)

        assert result == TENANT_A

    def test_returns_none_when_no_match(self) -> None:
        dao = self._make_dao_returning(None)

        result = dao.find_tenant_by_identity('+15559999', BACKEND)

        assert result is None


class _StubConnector:
    backend = BACKEND
    supported_types = ('sms',)

    @classmethod
    def normalize_identity(cls, raw_identity: str) -> str:
        return raw_identity


class TestConnectorServiceIdentityCRUD(unittest.TestCase):
    def _build_service(self) -> ConnectorService:
        dao = Mock()
        registry = ConnectorRegistry()
        registry.register_backend(_StubConnector)  # type: ignore[arg-type]
        return ConnectorService(dao, registry, Mock(), Mock())

    def test_list_identities(self) -> None:
        service = self._build_service()
        identity = _make_identity()
        service._dao.user_identity.list_by_user.return_value = [identity]

        result = service.list_identities([TENANT_A], USER_UUID)

        assert result == [identity]
        service._dao.user_identity.list_by_user.assert_called_once_with(
            USER_UUID, tenant_uuids=[TENANT_A]
        )

    def test_get_identity(self) -> None:
        service = self._build_service()
        identity = _make_identity()
        service._dao.user_identity.get.return_value = identity

        result = service.get_identity([TENANT_A], IDENTITY_UUID, user_uuid=USER_UUID)

        assert result is identity

    def test_create_identity(self) -> None:
        service = self._build_service()
        identity = _make_identity()
        service._dao.user_identity.create.return_value = identity

        result = service.create_identity(identity)

        assert result is identity
        service._dao.user_identity.create.assert_called_once_with(identity)

    def test_update_identity(self) -> None:
        service = self._build_service()
        identity = _make_identity()

        result = service.update_identity(identity)

        assert result is identity
        service._dao.user_identity.update.assert_called_once_with(identity)

    def test_create_identity_normalizes_value(self) -> None:
        service = self._build_service()
        identity = _make_identity(identity='  +15551234  ')
        service._dao.user_identity.create.return_value = identity

        with patch.object(
            _StubConnector, 'normalize_identity', return_value='+15551234'
        ):
            service.create_identity(identity)

        assert identity.identity == '+15551234'

    def test_create_identity_invalid_format_raises(self) -> None:
        service = self._build_service()
        identity = _make_identity(identity='not-valid')

        with patch.object(
            _StubConnector, 'normalize_identity', side_effect=ValueError('bad format')
        ):
            with pytest.raises(InvalidIdentityFormatException):
                service.create_identity(identity)

    def test_create_identity_unknown_backend_raises(self) -> None:
        service = self._build_service()
        identity = _make_identity(backend='nonexistent')

        with pytest.raises(UnknownBackendException):
            service.create_identity(identity)

    def test_update_identity_normalizes_value(self) -> None:
        service = self._build_service()
        identity = _make_identity(identity='  +15551234  ')

        with patch.object(
            _StubConnector, 'normalize_identity', return_value='+15551234'
        ):
            service.update_identity(identity)

        assert identity.identity == '+15551234'

    def test_delete_identity(self) -> None:
        service = self._build_service()
        identity = _make_identity()

        service.delete_identity(identity)

        service._dao.user_identity.delete.assert_called_once_with(identity)


class TestConnectorServiceGetUserTenantUuid(unittest.TestCase):
    def _build_service(self) -> ConnectorService:
        dao = Mock()
        dao.user.get.side_effect = UnknownUserException(USER_UUID)
        registry = ConnectorRegistry()
        return ConnectorService(dao, registry, Mock(), Mock())

    def _http_error(self, status: int) -> HTTPError:
        response = Mock(status_code=status)
        return HTTPError(response=response)

    def test_404_from_auth_raises_unknown_user(self) -> None:
        service = self._build_service()
        service._auth_client.users.get.side_effect = self._http_error(404)

        with pytest.raises(UnknownUserException):
            service.get_user_tenant_uuid([TENANT_A], USER_UUID)

    def test_500_from_auth_raises_auth_unavailable(self) -> None:
        service = self._build_service()
        service._auth_client.users.get.side_effect = self._http_error(500)

        with pytest.raises(AuthServiceUnavailableException):
            service.get_user_tenant_uuid([TENANT_A], USER_UUID)

    def test_401_from_auth_raises_auth_unavailable(self) -> None:
        service = self._build_service()
        service._auth_client.users.get.side_effect = self._http_error(401)

        with pytest.raises(AuthServiceUnavailableException):
            service.get_user_tenant_uuid([TENANT_A], USER_UUID)

    def test_connection_error_raises_auth_unavailable(self) -> None:
        service = self._build_service()
        service._auth_client.users.get.side_effect = RequestsConnectionError()

        with pytest.raises(AuthServiceUnavailableException):
            service.get_user_tenant_uuid([TENANT_A], USER_UUID)


class TestConnectorServiceResolveRoomParticipants(unittest.TestCase):
    def _build_service(self) -> ConnectorService:
        dao = Mock()
        registry = ConnectorRegistry()
        registry.register_backend(_StubConnector)  # type: ignore[arg-type]
        return ConnectorService(dao, registry, Mock(), Mock())

    def test_uuid_only_participant_unchanged(self) -> None:
        service = self._build_service()
        body = {'users': [{'uuid': 'user-uuid-1'}]}

        service.resolve_room_participants(body, 'tenant-uuid')

        assert body['users'] == [{'uuid': 'user-uuid-1'}]

    def test_identity_resolved_to_wazo_user(self) -> None:
        service = self._build_service()
        wazo_user = Mock(uuid='resolved-uuid')
        service._dao.user_identity.resolve_users_by_identities.return_value = {
            '+15551234': wazo_user
        }
        body = {'users': [{'identity': '+15551234'}]}

        service.resolve_room_participants(body, 'tenant-uuid')

        assert body['users'] == [{'uuid': 'resolved-uuid'}]

    def test_identity_not_resolved_gets_uuid5(self) -> None:
        service = self._build_service()
        service._dao.user_identity.resolve_users_by_identities.return_value = {}
        body = {'users': [{'identity': '+15559876'}]}

        service.resolve_room_participants(body, 'tenant-uuid')

        expected_uuid = str(make_uuid5('tenant-uuid', '+15559876'))
        assert body['users'] == [{'uuid': expected_uuid, 'identity': '+15559876'}]

    def test_mixed_participants(self) -> None:
        service = self._build_service()
        wazo_user = Mock(uuid='resolved-uuid')
        service._dao.user_identity.resolve_users_by_identities.return_value = {
            '+15551234': wazo_user
        }
        body = {
            'users': [
                {'uuid': 'existing-uuid'},
                {'identity': '+15551234'},
                {'identity': '+15559876'},
            ]
        }

        service.resolve_room_participants(body, 'tenant-uuid')

        assert body['users'][0] == {'uuid': 'existing-uuid'}
        assert body['users'][1] == {'uuid': 'resolved-uuid'}
        assert 'identity' not in body['users'][1]
        assert body['users'][2]['uuid'] is not None
        assert body['users'][2]['identity'] == '+15559876'

    def test_no_users_key_does_nothing(self) -> None:
        service = self._build_service()
        body: dict = {}

        service.resolve_room_participants(body, 'tenant-uuid')

        assert body == {}
