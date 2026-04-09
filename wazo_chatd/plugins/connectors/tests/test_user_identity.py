# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import Mock

from wazo_chatd.database.models import UserIdentity
from wazo_chatd.database.queries.user_identity import UserIdentityDAO
from wazo_chatd.exceptions import UnknownUserIdentityException
from wazo_chatd.plugins.connectors.services import ConnectorService

TENANT_A = 'tenant-a-uuid'
USER_UUID = 'user-uuid'
IDENTITY_UUID = 'identity-uuid'


def _make_identity(
    identity_uuid: str = IDENTITY_UUID,
    user_uuid: str = USER_UUID,
    tenant_uuid: str = TENANT_A,
    backend: str = 'twilio',
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


class TestConnectorServiceIdentityCRUD(unittest.TestCase):
    def _build_service(self) -> ConnectorService:
        from wazo_chatd.plugins.connectors.registry import ConnectorRegistry

        dao = Mock()
        registry = ConnectorRegistry()
        return ConnectorService(dao, registry, Mock())

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

    def test_delete_identity(self) -> None:
        service = self._build_service()
        identity = _make_identity()

        service.delete_identity(identity)

        service._dao.user_identity.delete.assert_called_once_with(identity)
