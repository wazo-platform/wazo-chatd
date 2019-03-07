# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from requests import HTTPError

from xivo.tenant_flask_helpers import (
    Tenant,
    auth_client,
    token,
)


def get_tenant_uuids(recurse=False):
    tenant = Tenant.autodetect().uuid

    if not recurse:
        return [tenant]

    auth_client.set_token(token.uuid)

    try:
        tenants = auth_client.tenants.list(tenant_uuid=tenant)['items']
    except HTTPError as e:
        response = getattr(e, 'response', None)
        status_code = getattr(response, 'status_code', None)
        if status_code == 401:
            return [tenant]
        raise

    return [tenant['uuid'] for tenant in tenants]
