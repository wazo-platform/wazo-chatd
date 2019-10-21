# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from wazo_chatd.exceptions import UnknownUserException
from wazo_chatd.database.helpers import session_scope
from wazo_chatd.database.models import Endpoint, Line, Session, Tenant, User
from .initiator import DEVICE_STATE_MAP, extract_endpoint_name

logger = logging.getLogger(__name__)

INUSE_STATE = (
    'holding',
    'ringing',
    'talking',
)


class BusEventHandler:
    def __init__(self, dao, notifier):
        self._dao = dao
        self._notifier = notifier

    def subscribe(self, bus_consumer):
        bus_consumer.on_event('auth_tenant_created', self._tenant_created)
        bus_consumer.on_event('auth_tenant_deleted', self._tenant_deleted)
        bus_consumer.on_event('user_created', self._user_created)
        bus_consumer.on_event('user_deleted', self._user_deleted)
        bus_consumer.on_event('auth_session_created', self._session_created)
        bus_consumer.on_event('auth_session_deleted', self._session_deleted)
        bus_consumer.on_event('user_line_associated', self._user_line_associated)
        bus_consumer.on_event('user_line_dissociated', self._user_line_dissociated)
        bus_consumer.on_event('DeviceStateChange', self._device_state_change)
        bus_consumer.on_event('Hangup', self._channel_deleted)
        bus_consumer.on_event('Newchannel', self._channel_created)

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
            session = Session(uuid=session_uuid, user_uuid=user_uuid)
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

    def _user_line_associated(self, event):
        line_id = event['line']['id']
        user_uuid = event['user']['uuid']
        tenant_uuid = event['user']['tenant_uuid']
        endpoint_name = extract_endpoint_name(event['line'])
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
            endpoint = self._dao.endpoint.find_by(name=endpoint_name)
            if not endpoint:
                endpoint = self._dao.endpoint.create(Endpoint(name=endpoint_name))
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

    def _device_state_change(self, event):
        endpoint_name = event['Device']
        state = DEVICE_STATE_MAP.get(event['State'], 'unavailable')
        with session_scope():
            endpoint = self._dao.endpoint.find_by(name=endpoint_name)
            if not endpoint:
                endpoint = self._dao.endpoint.create(Endpoint(name=endpoint_name))
            if (
                (state in INUSE_STATE and endpoint.channel_state == 'down')
                or (state not in INUSE_STATE and endpoint.channel_state == 'up')
            ):
                logger.debug(
                    'Invalid endpoint "%s" state "%s", channel state is "%s"',
                    endpoint_name,
                    state,
                    endpoint.channel_state,
                )
                return
            endpoint.state = state
            logger.debug(
                'Update endpoint "%s" with state "%s"', endpoint.name, endpoint.state
            )
            self._dao.endpoint.update(endpoint)
            if endpoint.line:
                self._notifier.updated(endpoint.line.user)

    def _channel_created(self, event):
        endpoint_name = self._extract_endpoint_from_channel(event['Channel'])
        if not endpoint_name:
            return

        with session_scope():
            endpoint = self._dao.endpoint.find_by(name=endpoint_name)
            if not endpoint:
                endpoint = self._dao.endpoint.create(Endpoint(name=endpoint_name))
            endpoint.channel_state = 'up'
            logger.debug(
                'Update endpoint "%s" with state "%s" and channel state "%s"',
                endpoint.name,
                endpoint.state,
                endpoint.channel_state,
            )
            self._dao.endpoint.update(endpoint)

    def _channel_deleted(self, event):
        endpoint_name = self._extract_endpoint_from_channel(event['Channel'])
        if not endpoint_name:
            return

        with session_scope():
            endpoint = self._dao.endpoint.find_by(name=endpoint_name)
            if not endpoint:
                endpoint = self._dao.endpoint.create(Endpoint(name=endpoint_name))
            old_endpoint_state = endpoint.state
            endpoint.channel_state = 'down'
            if endpoint.state in INUSE_STATE:
                endpoint.state = 'available'
            logger.debug(
                'Update endpoint "%s" with state "%s" and channel state "%s"',
                endpoint.name,
                endpoint.state,
                endpoint.channel_state,
            )
            self._dao.endpoint.update(endpoint)
            if endpoint.line and old_endpoint_state != endpoint.state:
                self._notifier.updated(endpoint.line.user)

    def _extract_endpoint_from_channel(self, channel_name):
        endpoint_name = '-'.join(channel_name.split('-')[:-1])
        if not endpoint_name:
            logger.debug('Invalid endpoint from channel "%s"', channel_name)
            return
        return endpoint_name
