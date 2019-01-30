# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from ..helpers import get_dao_session
from ..models import Tenant


class TenantDAO:

    @property
    def session(self):
        return get_dao_session()

    def find_or_create(self, tenant_uuid):
        result = self.session.query(Tenant).get(tenant_uuid)
        if result:
            return result

        tenant = Tenant(uuid=tenant_uuid)
        self.session.add(tenant)
        self.session.flush()

        return tenant

    def delete(self, tenant):
        self.session.delete(tenant)
        self.session.flush()
