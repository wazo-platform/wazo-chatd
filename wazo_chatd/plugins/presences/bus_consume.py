# Copyright 2019-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from wazo_chatd.exceptions import UnknownUserException
from wazo_chatd.database.helpers import session_scope
from wazo_chatd.database.models import (
    Channel,
    Line,
    RefreshToken,
    Session,
    Tenant,
    User,
)
from .initiator import (
    CHANNEL_STATE_MAP,
    DEVICE_STATE_MAP,
    extract_endpoint_from_line,
    extract_endpoint_from_channel,
)

logger = logging.getLogger(__name__)


class BusEventHandler:
    def __init__(self, dao, notifier):
        self._dao = dao
        self._notifier = notifier

    def subscribe(self, bus_consumer):
        events = [
            ('auth_tenant_added', self._tenant_created),
            ('auth_tenant_deleted', self._tenant_deleted),
            ('user_created', self._user_created),
            ('user_deleted', self._user_deleted),
            ('auth_session_created', self._session_created),
            ('auth_session_deleted', self._session_deleted),
            ('auth_refresh_token_created', self._refresh_token_created),
            ('auth_refresh_token_deleted', self._refresh_token_deleted),
            ('user_line_associated', self._user_line_associated),
            ('user_line_dissociated', self._user_line_dissociated),
            ('users_services_dnd_updated', self._user_dnd_updated),
            ('DeviceStateChange', self._device_state_change),
            ('Hangup', self._channel_deleted),
            ('Newchannel', self._channel_created),
            ('Newstate', self._channel_updated),
            ('Hold', self._channel_hold),
            ('Unhold', self._channel_unhold),
        ]

        for event, handler in events:
            bus_consumer.subscribe(event, handler)

    def _user_created(self, event):
        user_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            tenant = self._dao.tenant.find_or_create(tenant_uuid)
            logger.debug('Create user "%s"', user_uuid)
            user = User(uuid=user_uuid, tenant=tenant, state='unavailable')
            self._dao.user.create(user)

    def _user_deleted(self, event):
        user_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        with session_scope():
            user = self._dao.user.get([tenant_uuid], user_uuid)
            logger.debug('Delete user "%s"', user_uuid)
            self._dao.user.delete(user)

    def _tenant_created(self, event):
        tenant_uuid = event['uuid']
        with session_scope():
            logger.debug('Create tenant "%s"', tenant_uuid)
            tenant = Tenant(uuid=tenant_uuid)
            self._dao.tenant.create(tenant)

    def _tenant_deleted(self, event):
        tenant_uuid = event['uuid']
        with session_scope():
            tenant = self._dao.tenant.get(tenant_uuid)
            logger.debug('Delete tenant "%s"', tenant_uuid)
            self._dao.tenant.delete(tenant)

    def _session_created(self, event):
        mobile = event['mobile']
        session_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        user_uuid = event['user_uuid']
        with session_scope():
            try:
                user = self._dao.user.get([tenant_uuid], user_uuid)
            except UnknownUserException:
                logger.debug(
                    'Session "%s" has no valid user "%s"', session_uuid, user_uuid
                )
                return

            logger.debug('Create session "%s" for user "%s"', session_uuid, user_uuid)
            session = Session(uuid=session_uuid, user_uuid=user_uuid, mobile=mobile)
            self._dao.user.add_session(user, session)
            self._notifier.updated(user)

    def _session_deleted(self, event):
        session_uuid = event['uuid']
        tenant_uuid = event['tenant_uuid']
        user_uuid = event['user_uuid']
        with session_scope():
            try:
                user = self._dao.user.get([tenant_uuid], user_uuid)
            except UnknownUserException:
                logger.debug(
                    'Session "%s" has no valid user "%s"', session_uuid, user_uuid
                )
                return

            session = self._dao.session.get(session_uuid)
            logger.debug('Delete session "%s" for user "%s"', session_uuid, user_uuid)
            self._dao.user.remove_session(user, session)
            self._notifier.updated(user)

    def _refresh_token_created(self, event):
        mobile = event['mobile']
        tenant_uuid = event['tenant_uuid']
        user_uuid = event['user_uuid']
        client_id = event['client_id']
        with session_scope():
            try:
                user = self._dao.user.get([tenant_uuid], user_uuid)
            except UnknownUserException:
                logger.debug(
                    'Refresh token "%s" has no valid user "%s"', client_id, user_uuid
                )
                return

            logger.debug(
                'Create refresh token "%s" for user "%s"', client_id, user_uuid
            )
            refresh_token = RefreshToken(
                client_id=client_id, user_uuid=user_uuid, mobile=mobile
            )
            self._dao.user.add_refresh_token(user, refresh_token)
            self._notifier.updated(user)

    def _refresh_token_deleted(self, event):
        tenant_uuid = event['tenant_uuid']
        user_uuid = event['user_uuid']
        client_id = event['client_id']
        with session_scope():
            try:
                user = self._dao.user.get([tenant_uuid], user_uuid)
            except UnknownUserException:
                logger.debug(
                    'Refresh token "%s" has no valid user "%s"', client_id, user_uuid
                )
                return

            refresh_token = self._dao.refresh_token.get(user_uuid, client_id)
            logger.debug(
                'Delete refresh token "%s" for user "%s"', client_id, user_uuid
            )
            self._dao.user.remove_refresh_token(user, refresh_token)
            self._notifier.updated(user)

    def _user_line_associated(self, event):
        line_id = event['line']['id']
        user_uuid = event['user']['uuid']
        tenant_uuid = event['user']['tenant_uuid']
        endpoint_name = extract_endpoint_from_line(event['line'])
        with session_scope():
            user = self._dao.user.get([tenant_uuid], user_uuid)
            line = self._dao.line.find(line_id)
            if not line:
                line = Line(id=line_id)
            logger.debug('Associate user "%s" with line "%s"', user_uuid, line_id)
            self._dao.user.add_line(user, line)

            if not endpoint_name:
                logger.warning('Line "%s" doesn\'t have name', line_id)
                self._notifier.updated(user)
                return
            endpoint = self._dao.endpoint.find_or_create(endpoint_name)
            logger.debug(
                'Associate line "%s" with endpoint "%s"', line_id, endpoint_name
            )
            self._dao.line.associate_endpoint(line, endpoint)
            self._notifier.updated(user)

    def _user_line_dissociated(self, event):
        line_id = event['line']['id']
        user_uuid = event['user']['uuid']
        tenant_uuid = event['user']['tenant_uuid']
        with session_scope():
            user = self._dao.user.get([tenant_uuid], user_uuid)
            line = self._dao.line.get(line_id)
            logger.debug('Delete line "%s"', line_id)
            self._dao.user.remove_line(user, line)
            self._notifier.updated(user)

    def _user_dnd_updated(self, event):
        user_uuid = event['user_uuid']
        tenant_uuid = event['tenant_uuid']
        enabled = event['enabled']
        with session_scope():
            user = self._dao.user.get([tenant_uuid], user_uuid)
            logger.debug('Updating DND status of user "%s" to "%s"', user_uuid, enabled)
            user.do_not_disturb = enabled
            self._dao.user.update(user)
            self._notifier.updated(user)

    def _device_state_change(self, event):
        endpoint_name = event['Device']
        if endpoint_name.startswith('Custom:'):
            return

        state = DEVICE_STATE_MAP.get(event['State'], 'unavailable')
        with session_scope():
            endpoint = self._dao.endpoint.find_or_create(endpoint_name)
            if endpoint.state == state:
                return

            endpoint.state = state
            logger.debug(
                'Update endpoint "%s" with state "%s"', endpoint.name, endpoint.state
            )
            self._dao.endpoint.update(endpoint)

            if endpoint.line:
                self._notifier.updated(endpoint.line.user)

    def _channel_created(self, event):
        channel_name = event['Channel']
        state = CHANNEL_STATE_MAP.get(event['ChannelStateDesc'], 'undefined')
        endpoint_name = extract_endpoint_from_channel(channel_name)
        with session_scope():
            line = self._dao.line.find_by(endpoint_name=endpoint_name)
            if not line:
                logger.debug(
                    'Unknown line with endpoint "%s" for channel "%s"',
                    endpoint_name,
                    channel_name,
                )
                return

            channel = Channel(name=channel_name, state=state)
            logger.debug('Create channel "%s" for line "%s"', channel.name, line.id)
            self._dao.line.add_channel(line, channel)

            self._notifier.updated(channel.line.user)

    def _channel_deleted(self, event):
        channel_name = event['Channel']
        with session_scope():
            channel = self._dao.channel.find(channel_name)
            if not channel:
                logger.debug('Unknown channel "%s"', channel_name)
                return

            logger.debug('Delete channel "%s"', channel_name)
            self._dao.line.remove_channel(channel.line, channel)

            self._notifier.updated(channel.line.user)

    def _channel_updated(self, event):
        channel_name = event['Channel']
        state = CHANNEL_STATE_MAP.get(event['ChannelStateDesc'], 'undefined')
        with session_scope():
            channel = self._dao.channel.find(channel_name)
            if not channel:
                logger.debug('Unknown channel "%s"', channel_name)
                return

            logger.debug('Update channel "%s" with state "%s"', channel_name, state)
            channel.state = state
            self._dao.channel.update(channel)

            self._notifier.updated(channel.line.user)

    def _channel_hold(self, event):
        channel_name = event['Channel']
        with session_scope():
            channel = self._dao.channel.find(channel_name)
            if not channel:
                logger.debug('Unknown channel "%s"', channel_name)
                return

            logger.debug('Update channel "%s" with state "holding"', channel_name)
            channel.state = 'holding'
            self._dao.channel.update(channel)

            self._notifier.updated(channel.line.user)

    def _channel_unhold(self, event):
        channel_name = event['Channel']
        state = CHANNEL_STATE_MAP.get(event['ChannelStateDesc'], 'undefined')
        with session_scope():
            channel = self._dao.channel.find(channel_name)
            if not channel:
                logger.debug('Unknown channel "%s"', channel_name)
                return

            logger.debug('Update channel "%s" with state "%s"', channel_name, state)
            channel.state = state
            self._dao.channel.update(channel)

            self._notifier.updated(channel.line.user)
