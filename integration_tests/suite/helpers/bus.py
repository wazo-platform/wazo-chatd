# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo_test_helpers import bus as bus_helper


class BusClient(bus_helper.BusClient):

    def send_tenant_created_event(self, tenant_uuid):
        self.publish({
            'data': {
                'uuid': tenant_uuid,
            },
            'name': 'auth_tenant_created',
        }, 'auth.tenants.{}.created'.format(tenant_uuid))

    def send_tenant_deleted_event(self, tenant_uuid):
        self.publish({
            'data': {
                'uuid': tenant_uuid,
            },
            'name': 'auth_tenant_deleted',
        }, 'auth.tenants.{}.deleted'.format(tenant_uuid))

    def send_user_created_event(self, user_uuid, tenant_uuid):
        self.publish({
            'data': {
                'uuid': user_uuid,
                'tenant_uuid': tenant_uuid,
            },
            'name': 'user_created',
        }, 'config.user.created')

    def send_user_deleted_event(self, user_uuid, tenant_uuid):
        self.publish({
            'data': {
                'uuid': user_uuid,
                'tenant_uuid': tenant_uuid,
            },
            'name': 'user_deleted',
        }, 'config.user.deleted')

    def send_session_created_event(self, session_uuid, user_uuid, tenant_uuid):
        self.publish({
            'data': {
                'uuid': session_uuid,
                'user_uuid': user_uuid,
                'tenant_uuid': tenant_uuid,
            },
            'name': 'auth_session_created',
        }, 'auth.sessions.{}.created'.format(session_uuid))

    def send_session_deleted_event(self, session_uuid, user_uuid, tenant_uuid):
        self.publish({
            'data': {
                'uuid': session_uuid,
                'user_uuid': user_uuid,
                'tenant_uuid': tenant_uuid,
            },
            'name': 'auth_session_deleted',
        }, 'auth.sessions.{}.deleted'.format(session_uuid))
