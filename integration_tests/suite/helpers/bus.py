# Copyright 2019-2020 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo_test_helpers import bus as bus_helper


class BusClient(bus_helper.BusClient):
    def send_tenant_created_event(self, tenant_uuid):
        self.publish(
            {'data': {'uuid': str(tenant_uuid)}, 'name': 'auth_tenant_added'},
            'auth.tenants.{}.created'.format(tenant_uuid),
        )

    def send_tenant_deleted_event(self, tenant_uuid):
        self.publish(
            {'data': {'uuid': str(tenant_uuid)}, 'name': 'auth_tenant_deleted'},
            'auth.tenants.{}.deleted'.format(tenant_uuid),
        )

    def send_user_created_event(self, user_uuid, tenant_uuid):
        self.publish(
            {
                'data': {'uuid': str(user_uuid), 'tenant_uuid': str(tenant_uuid)},
                'name': 'user_created',
            },
            'config.user.created',
        )

    def send_user_deleted_event(self, user_uuid, tenant_uuid):
        self.publish(
            {
                'data': {'uuid': str(user_uuid), 'tenant_uuid': str(tenant_uuid)},
                'name': 'user_deleted',
            },
            'config.user.deleted',
        )

    def send_session_created_event(
        self, session_uuid, user_uuid, tenant_uuid, mobile=False
    ):
        self.publish(
            {
                'data': {
                    'uuid': str(session_uuid),
                    'user_uuid': str(user_uuid),
                    'tenant_uuid': str(tenant_uuid),
                    'mobile': mobile,
                },
                'name': 'auth_session_created',
            },
            'auth.sessions.{}.created'.format(session_uuid),
        )

    def send_session_deleted_event(self, session_uuid, user_uuid, tenant_uuid):
        self.publish(
            {
                'data': {
                    'uuid': str(session_uuid),
                    'user_uuid': str(user_uuid),
                    'tenant_uuid': str(tenant_uuid),
                },
                'name': 'auth_session_deleted',
            },
            'auth.sessions.{}.deleted'.format(session_uuid),
        )

    def send_refresh_token_created_event(
        self, client_id, user_uuid, tenant_uuid, mobile=False
    ):
        self.publish(
            {
                'data': {
                    'client_id': client_id,
                    'user_uuid': str(user_uuid),
                    'tenant_uuid': str(tenant_uuid),
                    'mobile': mobile,
                },
                'name': 'auth_refresh_token_created',
            },
            'auth.users.{}.tokens.{}.created'.format(user_uuid, client_id),
        )

    def send_refresh_token_deleted_event(self, client_id, user_uuid, tenant_uuid):
        self.publish(
            {
                'data': {
                    'client_id': client_id,
                    'user_uuid': str(user_uuid),
                    'tenant_uuid': str(tenant_uuid),
                },
                'name': 'auth_refresh_token_deleted',
            },
            'auth.users.{}.tokens.{}.deleted'.format(user_uuid, client_id),
        )

    def send_user_line_associated_event(
        self, line_id, user_uuid, tenant_uuid, line_name
    ):
        self.publish(
            {
                'data': {
                    'line': {
                        'id': line_id,
                        'name': line_name,
                        'endpoint_sip': {'id': 1},
                        'endpoint_sccp': {},
                        'endpoint_custom': {},
                    },
                    'user': {'uuid': str(user_uuid), 'tenant_uuid': str(tenant_uuid)},
                },
                'name': 'user_line_associated',
            },
            'config.users.{}.lines.{}.updated'.format(user_uuid, line_id),
        )

    def send_line_dissociated_event(self, line_id, user_uuid, tenant_uuid):
        self.publish(
            {
                'data': {
                    'line': {
                        'id': line_id,
                        'name': None,
                        'endpoint_sip': {'id': 1},
                        'endpoint_sccp': {},
                        'endpoint_custom': {},
                    },
                    'user': {'uuid': str(user_uuid), 'tenant_uuid': str(tenant_uuid)},
                },
                'name': 'user_line_dissociated',
            },
            'config.users.{}.lines.{}.deleted'.format(user_uuid, line_id),
        )

    def send_device_state_changed_event(self, device_name, device_state):
        self.publish(
            {
                'data': {'State': device_state, 'Device': device_name},
                'name': 'DeviceStateChange',
            },
            'ami.DeviceStateChange',
        )

    def send_new_channel_event(self, channel_name):
        self.publish(
            {
                'data': {'Channel': channel_name, 'ChannelStateDesc': 'Ring'},
                'name': 'Newchannel'
            },
            'ami.Newchannel',
        )

    def send_hangup_event(self, channel_name):
        self.publish(
            {'data': {'Channel': channel_name}, 'name': 'Hangup'}, 'ami.Hangup',
        )
