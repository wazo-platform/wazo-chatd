# Copyright 2019-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import assert_that, calling, equal_to, has_items, has_properties
from sqlalchemy.inspection import inspect
from wazo_test_helpers.hamcrest.raises import raises

from wazo_chatd.database.models import Tenant
from wazo_chatd.exceptions import UnknownTenantException

from .helpers import fixtures
from .helpers.base import DBIntegrationTest, use_asset

UNKNOWN_UUID = uuid.uuid4()


@use_asset('database')
class TestTenant(DBIntegrationTest):
    def test_find_or_create(self):
        tenant_uuid = uuid.uuid4()
        created_tenant = self._dao.tenant.find_or_create(tenant_uuid)

        self._session.expire_all()
        assert_that(inspect(created_tenant).persistent)
        assert_that(created_tenant, has_properties(uuid=tenant_uuid))

        found_tenant = self._dao.tenant.find_or_create(created_tenant.uuid)
        assert_that(found_tenant, has_properties(uuid=created_tenant.uuid))

        self._dao.tenant.delete(found_tenant)

    def test_create(self):
        tenant_uuid = uuid.uuid4()
        tenant = Tenant(uuid=tenant_uuid)
        tenant = self._dao.tenant.create(tenant)

        self._session.expire_all()
        assert_that(inspect(tenant).persistent)
        assert_that(tenant, has_properties(uuid=tenant_uuid))

        self._dao.tenant.delete(tenant)

    @fixtures.db.tenant()
    def test_get(self, tenant):
        result = self._dao.tenant.get(tenant.uuid)
        assert_that(result, equal_to(tenant))

        assert_that(
            calling(self._dao.tenant.get).with_args(UNKNOWN_UUID),
            raises(UnknownTenantException),
        )

    @fixtures.db.tenant()
    def test_delete(self, tenant):
        self._dao.tenant.delete(tenant)

        self._session.expire_all()
        assert_that(inspect(tenant).deleted)

    @fixtures.db.tenant()
    @fixtures.db.tenant()
    def test_list(self, tenant_1, tenant_2):
        tenants = self._dao.tenant.list_()
        assert_that(tenants, has_items(tenant_1, tenant_2))
