# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import (
    assert_that,
    has_properties,
)
from sqlalchemy.inspection import inspect

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
