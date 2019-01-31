# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from flask import request

from xivo.auth_verifier import required_acl

from wazo_chatd.http import AuthResource
from wazo_chatd.plugin_helpers.tenant import get_tenant_uuids

from .schemas import ListRequestSchema, UserPresenceSchema


class PresenceListResource(AuthResource):

    def __init__(self, service):
        self._service = service

    @required_acl('chatd.users.presences.read')
    def get(self):
        parameters = ListRequestSchema().load(request.args).data
        tenant_uuids = get_tenant_uuids(parameters.pop('recurse'))

        presences = self._service.list_(tenant_uuids, **parameters)
        total = self._service.count(tenant_uuids)
        filtered = self._service.count(tenant_uuids, **parameters)
        return {
            'items': UserPresenceSchema().dump(presences, many=True).data,
            'filtered': filtered,
            'total': total,
        }


class PresenceItemResource(AuthResource):

    def __init__(self, service):
        self._service = service

    @required_acl('chatd.users.{user_uuid}.presences.read')
    def get(self, user_uuid):
        tenant_uuids = get_tenant_uuids(recurse=True)
        presence = self._service.get(tenant_uuids, user_uuid)
        return UserPresenceSchema().dump(presence).data, 200
