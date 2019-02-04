# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import (
    assert_that,
    equal_to,
    has_properties,
    has_items,
)
from sqlalchemy.inspection import inspect

from wazo_chatd.database.models import Tenant
from .helpers import fixtures
from .helpers.base import BaseIntegrationTest


class TestTenant(BaseIntegrationTest):

    asset = 'database'
    service = 'postgresql'

    def test_find_or_create(self):
        tenant_uuid = str(uuid.uuid4())
        created_tenant = self._tenant_dao.find_or_create(tenant_uuid)

        self._session.expire_all()
        assert_that(inspect(created_tenant).persistent)
        assert_that(created_tenant, has_properties(uuid=tenant_uuid))

        found_tenant = self._tenant_dao.find_or_create(created_tenant.uuid)
        assert_that(found_tenant, has_properties(uuid=created_tenant.uuid))

        self._tenant_dao.delete(found_tenant)

    def test_create(self):
        tenant_uuid = uuid.uuid4()
        tenant = Tenant(uuid=tenant_uuid)
        tenant = self._tenant_dao.create(tenant)

        self._session.expire_all()
        assert_that(inspect(tenant).persistent)
        assert_that(tenant, has_properties(uuid=str(tenant_uuid)))

        self._tenant_dao.delete(tenant)

    @fixtures.db.tenant()
    def test_get(self, tenant):
        tenant = self._tenant_dao.get(tenant.uuid)
        assert_that(tenant, equal_to(tenant))

    @fixtures.db.tenant()
    def test_delete(self, tenant):
        self._tenant_dao.delete(tenant)

        self._session.expire_all()
        assert_that(inspect(tenant).deleted)

    @fixtures.db.tenant()
    @fixtures.db.tenant()
    def test_list(self, tenant_1, tenant_2):
        tenants = self._tenant_dao.list_()
        assert_that(tenants, has_items(tenant_1, tenant_2))
