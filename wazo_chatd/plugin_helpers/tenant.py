# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from uuid import NAMESPACE_URL, UUID, uuid5

from xivo.tenant_flask_helpers import Tenant, token


def get_tenant_uuids(recurse=False):
    tenant_uuid = Tenant.autodetect().uuid
    if not recurse:
        return [tenant_uuid]
    return [tenant.uuid for tenant in token.visible_tenants(tenant_uuid)]


def make_uuid5(tenant_uuid: str, key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f'{tenant_uuid}:{key}')
