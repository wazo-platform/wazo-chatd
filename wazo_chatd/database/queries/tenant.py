# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from ...exceptions import UnknownTenantException
from ..helpers import bulk_delete, bulk_insert
from ..models import Tenant


class TenantDAO:
    def __init__(self, session):
        self._session = session

    @property
    def session(self):
        return self._session()

    def get(self, tenant_uuid):
        tenant = self.session.get(Tenant, tenant_uuid)
        if not tenant:
            raise UnknownTenantException(tenant_uuid)
        return tenant

    def list_(self):
        return self.session.query(Tenant).all()

    def list_uuids(self):
        return {str(uuid) for (uuid,) in self.session.query(Tenant.uuid).all()}

    def create(self, tenant):
        self.session.add(tenant)
        self.session.flush()
        return tenant

    def create_all(self, tenants):
        bulk_insert(self.session, tenants)

    def delete_by_uuids(self, uuids):
        bulk_delete(self.session, Tenant, Tenant.uuid, uuids)

    def find_or_create(self, tenant_uuid):
        result = self.session.get(Tenant, tenant_uuid)
        if result:
            return result

        tenant = Tenant(uuid=tenant_uuid)
        return self.create(tenant)

    def delete(self, tenant):
        self.session.delete(tenant)
        self.session.flush()
