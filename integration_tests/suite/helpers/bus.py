# Copyright 2019-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from wazo_test_helpers import bus as bus_helper

FAKE_UUID = str(uuid.uuid4())


class BusClient(bus_helper.BusClient):
    def send_tenant_created_event(self, tenant_uuid):
        self.publish(
            {
                'data': {
                    'uuid': str(tenant_uuid),
                },
                'name': 'auth_tenant_added',
            },
            headers={
                'name': 'auth_tenant_added',
                'tenant_uuid': str(tenant_uuid),
            },
            routing_key=f'auth.tenants.{tenant_uuid}.created',
        )

    def send_tenant_deleted_event(self, tenant_uuid):
        self.publish(
            {
                'data': {
                    'uuid': str(tenant_uuid),
                },
                'name': 'auth_tenant_deleted',
            },
            headers={
                'name': 'auth_tenant_deleted',
                'tenant_uuid': str(tenant_uuid),
            },
            routing_key=f'auth.tenants.{tenant_uuid}.deleted',
        )

    def send_user_created_event(self, user_uuid, tenant_uuid):
        self.publish(
            {
                'data': {
                    'uuid': str(user_uuid),
                    'tenant_uuid': str(tenant_uuid),
                },
                'name': 'user_created',
            },
            headers={
                'name': 'user_created',
                'tenant_uuid': str(tenant_uuid),
            },
            routing_key='config.user.created',
        )

    def send_user_deleted_event(self, user_uuid, tenant_uuid):
        self.publish(
            {
                'data': {'uuid': str(user_uuid), 'tenant_uuid': str(tenant_uuid)},
                'name': 'user_deleted',
            },
            headers={
                'name': 'user_deleted',
                'tenant_uuid': str(tenant_uuid),
            },
            routing_key='config.user.deleted',
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
            headers={
                'name': 'auth_session_created',
                'tenant_uuid': str(tenant_uuid),
            },
            routing_key='config.user.deleted',
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
            headers={
                'name': 'auth_session_deleted',
                'tenant_uuid': str(tenant_uuid),
            },
            routing_key=f'auth.sessions.{session_uuid}.deleted',
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
            headers={
                'name': 'auth_refresh_token_created',
                'tenant_uuid': str(tenant_uuid),
            },
            routing_key=f'auth.users.{user_uuid}.tokens.{client_id}.created',
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
            headers={
                'name': 'auth_refresh_token_deleted',
                'tenant_uuid': str(tenant_uuid),
            },
            routing_key=f'auth.users.{user_uuid}.tokens.{client_id}.deleted',
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
                        'endpoint_sip': {'uuid': FAKE_UUID},
                        'endpoint_sccp': {},
                        'endpoint_custom': {},
                    },
                    'user': {
                        'uuid': str(user_uuid),
                        'tenant_uuid': str(tenant_uuid),
                    },
                },
                'name': 'user_line_associated',
            },
            headers={
                'name': 'user_line_associated',
                'tenant_uuid': str(tenant_uuid),
            },
            routing_key=f'config.users.{user_uuid}.lines.{line_id}.updated',
        )

    def send_line_dissociated_event(self, line_id, user_uuid, tenant_uuid):
        self.publish(
            {
                'data': {
                    'line': {
                        'id': line_id,
                        'name': None,
                        'endpoint_sip': {'uuid': FAKE_UUID},
                        'endpoint_sccp': {},
                        'endpoint_custom': {},
                    },
                    'user': {
                        'uuid': str(user_uuid),
                        'tenant_uuid': str(tenant_uuid),
                    },
                },
                'name': 'user_line_dissociated',
            },
            headers={
                'name': 'user_line_dissociated',
                'tenant_uuid': str(tenant_uuid),
            },
            routing_key=f'config.users.{user_uuid}.lines.{line_id}.deleted',
        )

    def send_device_state_changed_event(self, device_name, device_state):
        self.publish(
            {
                'data': {
                    'State': device_state,
                    'Device': device_name,
                },
                'name': 'DeviceStateChange',
            },
            headers={
                'name': 'DeviceStateChange',
            },
            routing_key='ami.DeviceStateChange',
        )

    def send_new_channel_event(self, channel_name):
        self.publish(
            {
                'data': {
                    'Channel': channel_name,
                    'ChannelStateDesc': 'Ring',
                },
                'name': 'Newchannel',
            },
            headers={
                'name': 'Newchannel',
            },
            routing_key='ami.Newchannel',
        )

    def send_new_state_event(self, channel_name, state='undefined'):
        self.publish(
            {
                'data': {
                    'Channel': channel_name,
                    'ChannelStateDesc': state,
                },
                'name': 'Newstate',
            },
            headers={
                'name': 'Newstate',
            },
            routing_key='ami.Newstate',
        )

    def send_hangup_event(self, channel_name):
        self.publish(
            {
                'data': {
                    'Channel': channel_name,
                },
                'name': 'Hangup',
            },
            headers={
                'name': 'Hangup',
            },
            routing_key='ami.Hangup',
        )

    def send_hold_event(self, channel_name):
        self.publish(
            {
                'data': {
                    'Channel': channel_name,
                },
                'name': 'Hold',
            },
            headers={
                'name': 'Hold',
            },
            routing_key='ami.Hold',
        )

    def send_unhold_event(self, channel_name):
        self.publish(
            {
                'data': {
                    'Channel': channel_name,
                    'ChannelStateDesc': 'Up',
                },
                'name': 'Unhold',
            },
            headers={
                'name': 'Unhold',
            },
            routing_key='ami.Hold',
        )

    def send_dnd_event(self, user_uuid, tenant_uuid, status):
        self.publish(
            {
                'data': {
                    'user_uuid': str(user_uuid),
                    'tenant_uuid': str(tenant_uuid),
                    'enabled': status,
                },
                'name': 'users_services_dnd_updated',
            },
            headers={
                'name': 'users_services_dnd_updated',
                'tenant_uuid': str(tenant_uuid),
            },
            routing_key=f'config.users.{user_uuid}.services.dnd.updated',
        )
