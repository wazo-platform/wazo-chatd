# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

import pytest

from wazo_chatd.database.models import UserIdentity
from wazo_chatd.exceptions import (
    DuplicateIdentityException,
    UnknownUserIdentityException,
)

from .helpers import fixtures
from .helpers.base import TOKEN_SUBTENANT_UUID as TENANT_2
from .helpers.base import TOKEN_TENANT_UUID as TENANT_1
from .helpers.base import DBIntegrationTest, use_asset

USER_UUID_1 = uuid.uuid4()
USER_UUID_2 = uuid.uuid4()


@use_asset('database')
class TestUserIdentity(DBIntegrationTest):
    @fixtures.db.user(uuid=USER_UUID_1)
    def test_create(self, user):
        identity = UserIdentity(
            user_uuid=USER_UUID_1,
            tenant_uuid=TENANT_1,
            backend='sms_backend',
            type_='sms',
            identity='+15551234567',
        )

        created = self._dao.user_identity.create(identity)

        result = self._dao.user_identity.find(str(created.uuid))
        assert result is not None
        assert result.user_uuid == USER_UUID_1
        assert result.backend == 'sms_backend'
        assert result.identity == '+15551234567'

        self._session.expunge_all()

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551234567',
    )
    def test_get(self, user, identity):
        result = self._dao.user_identity.get([str(TENANT_1)], str(identity.uuid))

        assert result.uuid == identity.uuid
        assert result.backend == 'sms_backend'

        with pytest.raises(UnknownUserIdentityException):
            self._dao.user_identity.get([str(TENANT_1)], str(uuid.uuid4()))

    @fixtures.db.user(uuid=USER_UUID_1, tenant_uuid=TENANT_2)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        tenant_uuid=TENANT_2,
        backend='sms_backend',
        type_='sms',
        identity='+15551234567',
    )
    def test_get_wrong_tenant_raises(self, user, identity):
        with pytest.raises(UnknownUserIdentityException):
            self._dao.user_identity.get([str(TENANT_1)], str(identity.uuid))

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551234567',
    )
    def test_update(self, user, identity):
        identity.identity = '+15550000000'

        self._dao.user_identity.update(identity)

        self._session.expire_all()
        stored = self._dao.user_identity.find(str(identity.uuid))
        assert stored is not None
        assert stored.identity == '+15550000000'

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551234567',
    )
    def test_delete(self, user, identity):
        self._dao.user_identity.delete(identity)

        self._session.expire_all()
        assert self._dao.user_identity.find(str(identity.uuid)) is None

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551111111',
    )
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='sms_alt_backend',
        type_='sms',
        identity='+15552222222',
    )
    def test_list_by_user(self, user, identity_1, identity_2):
        results = self._dao.user_identity.list_by_user(str(USER_UUID_1))

        assert len(results) == 2

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user(uuid=USER_UUID_2)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551111111',
    )
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='sms_alt_backend',
        type_='sms',
        identity='+15551111122',
    )
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_2,
        backend='sms_backend',
        type_='sms',
        identity='+15552222222',
    )
    def test_list_identities_by_users_filters_by_backend(
        self, user_1, user_2, ident_1, ident_2, ident_3
    ):
        result = self._dao.user_identity.list_identities_by_users(
            [str(USER_UUID_1), str(USER_UUID_2)], backend='sms_backend'
        )

        assert result == {
            str(USER_UUID_1): '+15551111111',
            str(USER_UUID_2): '+15552222222',
        }

    @fixtures.db.user(uuid=USER_UUID_1)
    def test_list_identities_by_users_returns_empty_when_no_match(self, user):
        result = self._dao.user_identity.list_identities_by_users(
            [str(USER_UUID_1)], backend='sms_backend'
        )

        assert result == {}

    @fixtures.db.user(uuid=USER_UUID_1, tenant_uuid=TENANT_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        tenant_uuid=TENANT_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551111111',
    )
    @fixtures.db.user(uuid=USER_UUID_2, tenant_uuid=TENANT_2)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_2,
        tenant_uuid=TENANT_2,
        backend='sms_backend',
        type_='sms',
        identity='+15552222222',
    )
    def test_list_by_user_filters_by_tenant(
        self, user_1, identity_1, user_2, identity_2
    ):
        tenant_1_results = self._dao.user_identity.list_by_user(
            str(USER_UUID_1), tenant_uuids=[str(TENANT_1)]
        )
        assert len(tenant_1_results) == 1
        assert tenant_1_results[0].identity == '+15551111111'

        cross_tenant_results = self._dao.user_identity.list_by_user(
            str(USER_UUID_1), tenant_uuids=[str(TENANT_2)]
        )
        assert cross_tenant_results == []

    @fixtures.db.user(uuid=USER_UUID_1, tenant_uuid=TENANT_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        tenant_uuid=TENANT_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551234567',
    )
    def test_find_tenant_by_identity(self, user, identity):
        result = self._dao.user_identity.find_tenant_by_identity(
            '+15551234567', 'sms_backend'
        )

        assert result == str(TENANT_1)

    @fixtures.db.user(uuid=USER_UUID_1, tenant_uuid=TENANT_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        tenant_uuid=TENANT_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551234567',
    )
    def test_find_tenant_by_identity_unknown_returns_none(self, user, identity):
        assert (
            self._dao.user_identity.find_tenant_by_identity(
                '+15559999999', 'sms_backend'
            )
            is None
        )

    @fixtures.db.user(uuid=USER_UUID_1, tenant_uuid=TENANT_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        tenant_uuid=TENANT_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551234567',
    )
    def test_find_tenant_by_identity_wrong_backend_returns_none(self, user, identity):
        assert (
            self._dao.user_identity.find_tenant_by_identity(
                '+15551234567', 'sms_alt_backend'
            )
            is None
        )

    @fixtures.db.user(uuid=USER_UUID_1, tenant_uuid=TENANT_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        tenant_uuid=TENANT_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551234567',
    )
    def test_has_identities_for_backend_true_on_match(self, user, identity):
        assert (
            self._dao.user_identity.has_identities_for_backend(
                str(TENANT_1), 'sms_backend'
            )
            is True
        )

    def test_has_identities_for_backend_false_when_no_row(self):
        assert (
            self._dao.user_identity.has_identities_for_backend(
                str(TENANT_1), 'sms_backend'
            )
            is False
        )

    @fixtures.db.user(uuid=USER_UUID_1, tenant_uuid=TENANT_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        tenant_uuid=TENANT_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551234567',
    )
    def test_has_identities_for_backend_false_on_wrong_tenant(self, user, identity):
        assert (
            self._dao.user_identity.has_identities_for_backend(
                str(TENANT_2), 'sms_backend'
            )
            is False
        )

    @fixtures.db.user(uuid=USER_UUID_1, tenant_uuid=TENANT_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        tenant_uuid=TENANT_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551234567',
    )
    def test_has_identities_for_backend_false_on_wrong_backend(self, user, identity):
        assert (
            self._dao.user_identity.has_identities_for_backend(
                str(TENANT_1), 'other_backend'
            )
            is False
        )

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551234567',
    )
    def test_create_duplicate_raises(self, user, identity):
        duplicate = UserIdentity(
            user_uuid=USER_UUID_1,
            tenant_uuid=TENANT_1,
            backend='sms_backend',
            type_='sms',
            identity='+15551234567',
        )

        with pytest.raises(DuplicateIdentityException):
            self._dao.user_identity.create(duplicate)

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551111111',
    )
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='sms_backend',
        type_='sms',
        identity='+15552222222',
    )
    def test_update_to_duplicate_raises(self, user, original, other):
        other.identity = '+15551111111'

        with pytest.raises(DuplicateIdentityException):
            self._dao.user_identity.update(other)

    def test_ensure_tenant_and_user_exist_is_idempotent(self):
        tenant_uuid = str(uuid.uuid4())
        user_uuid = str(uuid.uuid4())

        self._dao.user_identity.ensure_tenant_and_user_exist(tenant_uuid, user_uuid)
        self._dao.user_identity.ensure_tenant_and_user_exist(tenant_uuid, user_uuid)

        assert self._dao.tenant.get(tenant_uuid) is not None
        assert self._dao.user.get([tenant_uuid], user_uuid) is not None

    @fixtures.db.user(uuid=USER_UUID_1, tenant_uuid=TENANT_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        tenant_uuid=TENANT_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551111111',
    )
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        tenant_uuid=TENANT_1,
        backend='email_backend',
        type_='email',
        identity='alice@example.com',
    )
    @fixtures.db.user(uuid=USER_UUID_2, tenant_uuid=TENANT_2)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_2,
        tenant_uuid=TENANT_2,
        backend='sms_backend',
        type_='sms',
        identity='+15552222222',
    )
    def test_list_tenant_backends_returns_distinct_pairs(
        self, user_1, ident_sms, ident_email, user_2, ident_sms_t2
    ):
        result = self._dao.user_identity.list_tenant_backends()

        pairs = {(str(t), b) for t, b in result}
        assert (str(TENANT_1), 'sms_backend') in pairs
        assert (str(TENANT_1), 'email_backend') in pairs
        assert (str(TENANT_2), 'sms_backend') in pairs

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551111111',
    )
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='email_backend',
        type_='email',
        identity='alice@example.com',
    )
    @fixtures.db.user(uuid=USER_UUID_2)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_2,
        backend='sms_backend',
        type_='sms',
        identity='+15552222222',
    )
    def test_list_types_by_users_returns_distinct_types_per_user(
        self, user_1, ident_sms, ident_email, user_2, ident_sms_2
    ):
        result = self._dao.user_identity.list_types_by_users(
            [str(USER_UUID_1), str(USER_UUID_2)]
        )

        assert result == {
            str(USER_UUID_1): {'sms', 'email'},
            str(USER_UUID_2): {'sms'},
        }

    def test_list_types_by_users_returns_empty_set_for_unknown_user(self):
        unknown = str(uuid.uuid4())

        result = self._dao.user_identity.list_types_by_users([unknown])

        assert result == {unknown: set()}

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551111111',
    )
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='sms_alt_backend',
        type_='sms',
        identity='+15552222222',
    )
    def test_list_bound_identities_returns_intersection(self, user, ident_1, ident_2):
        result = self._dao.user_identity.list_bound_identities(
            ['+15551111111', '+15553333333', '+15552222222']
        )

        assert result == {'+15551111111', '+15552222222'}

    def test_list_bound_identities_returns_empty_when_none_match(self):
        result = self._dao.user_identity.list_bound_identities(['+15559999999'])

        assert result == set()

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551234567',
    )
    def test_is_identity_bound_true_on_match(self, user, identity):
        assert self._dao.user_identity.is_identity_bound('+15551234567') is True

    def test_is_identity_bound_false_on_no_match(self):
        assert self._dao.user_identity.is_identity_bound('+15559999999') is False

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user(uuid=USER_UUID_2)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='sms_backend',
        type_='sms',
        identity='+15551111111',
    )
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_2,
        backend='sms_backend',
        type_='sms',
        identity='+15552222222',
    )
    def test_resolve_users_by_identities_maps_known_identities(
        self, user_1, user_2, ident_1, ident_2
    ):
        result = self._dao.user_identity.resolve_users_by_identities(
            ['+15551111111', '+15552222222', '+15559999999']
        )

        assert set(result.keys()) == {'+15551111111', '+15552222222'}
        assert result['+15551111111'].uuid == USER_UUID_1
        assert result['+15552222222'].uuid == USER_UUID_2

    def test_resolve_users_by_identities_returns_empty_when_none_match(self):
        result = self._dao.user_identity.resolve_users_by_identities(['+15559999999'])

        assert result == {}
