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

    def send_line_associated_event(self, line_id, user_uuid, tenant_uuid):
        self.publish({
            'data': {
                'line_id': line_id,
                'user_uuid': user_uuid,
                'tenant_uuid': tenant_uuid,
            },
            'name': 'line_associated',
        }, 'config.user_line_association.created')

    def send_line_dissociated_event(self, line_id, user_uuid, tenant_uuid):
        self.publish({
            'data': {
                'line_id': line_id,
                'user_uuid': user_uuid,
                'tenant_uuid': tenant_uuid,
            },
            'name': 'line_dissociated',
        }, 'config.user_line_association.deleted')

    def send_device_state_changed_event(self, device_name, device_state):
        self.publish({
            'data': {
                'State': device_state,
                'Device': device_name,
            },
            'name': 'DeviceStateChange',
        }, 'ami.DeviceStateChange')

    def send_line_device_associated_event(self, line_id, line_name):
        self.publish({
            'data': {
                'line': {
                    'id': line_id,
                    'name': line_name,
                    'endpoint_sip': {'id': 1},
                    'endpoint_sccp': {},
                    'endpoint_custom': {},
                },
                'device': {'id': 1},
            },
            'name': 'line_device_associated',
        }, 'config.lines.{}.devices.1.updated'.format(line_id))

    def send_line_device_dissociated_event(self, line_id):
        self.publish({
            'data': {
                'line': {
                    'id': line_id,
                    'name': None,
                    'endpoint_sip': {},
                    'endpoint_sccp': {},
                    'endpoint_custom': {},
                },
                'device': {'id': 1},
            },
            'name': 'line_device_dissociated',
        }, 'config.lines.{}.devices.1.deleted'.format(line_id))
