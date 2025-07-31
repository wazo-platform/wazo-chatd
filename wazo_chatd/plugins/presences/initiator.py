# Copyright 2019-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import threading
from dataclasses import dataclass
from functools import partial

from xivo.status import Status

from wazo_chatd.database.helpers import session_scope
from wazo_chatd.database.models import (
    Channel,
    Endpoint,
    Line,
    RefreshToken,
    Session,
    Tenant,
    User,
)
from wazo_chatd.exceptions import (
    UnknownEndpointException,
    UnknownLineException,
    UnknownRefreshTokenException,
    UnknownSessionException,
    UnknownTenantException,
    UnknownUserException,
)

logger = logging.getLogger(__name__)

DEVICE_STATE_MAP = {
    'INUSE': 'available',
    'UNAVAILABLE': 'unavailable',
    'NOT_INUSE': 'available',
    'RINGING': 'available',
    'ONHOLD': 'available',
    'RINGINUSE': 'available',
    'UNKNOWN': 'unavailable',
    'BUSY': 'unavailable',
    'INVALID': 'unavailable',
}
CHANNEL_STATE_MAP = {
    'Down': 'undefined',
    'Rsrvd': 'undefined',
    'OffHook': 'undefined',
    'Dialing': 'undefined',
    'Ring': 'progressing',
    'Ringing': 'ringing',
    'Up': 'talking',
    'Busy': 'talking',
    'Dialing Offhook': 'undefined',
    'Pre-ring': 'undefined',
    'Unknown': 'undefined',
}


@dataclass(frozen=True)
class FetchedFlags:
    CHANNEL: str = 'channel'
    DEVICE: str = 'device'
    REFRESH_TOKEN: str = 'refresh_token'
    SESSION: str = 'session'
    TENANT: str = 'tenant'
    USER: str = 'user'

    @classmethod
    def all(cls):
        return [
            cls.CHANNEL,
            cls.DEVICE,
            cls.REFRESH_TOKEN,
            cls.SESSION,
            cls.TENANT,
            cls.USER,
        ]


def extract_endpoint_from_channel(channel_name):
    endpoint_name = '-'.join(channel_name.split('-')[:-1])
    if not endpoint_name:
        logger.debug('Invalid endpoint from channel "%s"', channel_name)
        return
    return endpoint_name


def extract_endpoint_from_line(line):
    if not line['name']:
        return

    if line.get('endpoint_sip'):
        return f'PJSIP/{line["name"]}'
    elif line.get('endpoint_sccp'):
        return f'SCCP/{line["name"]}'
    elif line.get('endpoint_custom'):
        return line['name']


class Initiator:
    def __init__(self, dao, auth, amid, confd):
        self._dao = dao
        self._auth = auth
        self._amid = amid
        self._confd = confd
        self._is_initialized = threading.Event()
        self._in_progress = threading.Event()
        self.post_hooks = []
        self._fetched_resources = {
            flag: threading.Event() for flag in FetchedFlags.all()
        }

    def provide_status(self, status):
        status['presence_initialization']['status'] = (
            Status.ok if self.is_initialized() else Status.fail
        )

    def is_initialized(self):
        return self._is_initialized.is_set()

    def in_progress(self):
        return self._in_progress.is_set()

    def _paginate_proxy(self, callback, limit=1000):
        callback = partial(callback, recurse=True, limit=limit)
        result = callback(limit=limit, offset=0)
        total = result['total']
        items = result['items']
        offset = len(items)
        while offset < total:
            new_items = callback(offset=offset)['items']
            items.extend(new_items)
            offset += len(new_items)
        assert len(items) == total
        return {'items': items, 'total': total}

    def reset_initialized(self):
        self._is_initialized.clear()

    def execute_post_hooks(self):
        for hook in self.post_hooks:
            logger.debug('Executing post hook: %s', hook.__name__)
            try:
                hook()
            except Exception as e:
                logger.error(e)
                continue

    def _clear_flags(self):
        for event in self._fetched_resources.values():
            event.clear()

    def is_fetched(self, resource):
        return self._fetched_resources[resource].is_set()

    def initiate(self):
        self._clear_flags()
        self._in_progress.set()

        token = self._auth.token.new(expiration=120)['token']
        self._auth.set_token(token)
        self._amid.set_token(token)
        self._confd.set_token(token)

        logger.debug('Fetching tenants...')
        tenants = self._paginate_proxy(self._auth.tenants.list, limit=10000)['items']
        self._fetched_resources[FetchedFlags.TENANT].set()

        logger.debug('Fetching users...')
        users = self._paginate_proxy(self._confd.users.list, limit=1000)['items']
        self._fetched_resources[FetchedFlags.USER].set()

        logger.debug('Fetching sesions...')
        sessions = self._paginate_proxy(self._auth.sessions.list, limit=10000)['items']
        self._fetched_resources[FetchedFlags.SESSION].set()

        logger.debug('Fetching refresh tokens...')
        refresh_tokens = self._paginate_proxy(
            self._auth.refresh_tokens.list,
            limit=10000,
        )['items']
        self._fetched_resources[FetchedFlags.REFRESH_TOKEN].set()

        logger.debug('Fetching device states...')
        endpoint_events = self._amid.action('DeviceStateList')
        self._fetched_resources[FetchedFlags.DEVICE].set()

        logger.debug('Fetching channels...')
        channel_events = self._amid.action('CoreShowChannels')
        self._fetched_resources[FetchedFlags.CHANNEL].set()

        logger.debug('Fetching data done!')

        self.initiate_endpoints(endpoint_events)
        self.initiate_tenants(tenants)
        self.initiate_users(users)
        self.initiate_sessions(sessions)
        self.initiate_refresh_tokens(refresh_tokens)
        self.initiate_channels(channel_events)
        self.execute_post_hooks()
        self._clear_flags()
        self._in_progress.clear()
        self._is_initialized.set()
        logger.debug('Initialized completed')

    def initiate_tenants(self, tenants):
        tenants = {tenant['uuid'] for tenant in tenants}
        tenants_cached = {str(tenant.uuid) for tenant in self._dao.tenant.list_()}

        tenants_missing = tenants - tenants_cached
        with session_scope():
            for uuid in tenants_missing:
                logger.debug('Create tenant "%s"', uuid)
                tenant = Tenant(uuid=uuid)
                self._dao.tenant.create(tenant)

        tenants_expired = tenants_cached - tenants
        with session_scope():
            for uuid in tenants_expired:
                try:
                    tenant = self._dao.tenant.get(uuid)
                except UnknownTenantException as e:
                    logger.warning(e)
                    continue
                logger.debug('Delete tenant "%s"', uuid)
                self._dao.tenant.delete(tenant)

    def initiate_users(self, users):
        self._add_and_remove_users(users)
        self._add_and_remove_lines(users)
        self._add_missing_endpoints(users)  # disconnected SCCP endpoints are missing
        self._associate_line_endpoint(users)
        self._update_services_users(users)

    def _add_and_remove_users(self, users):
        users = {(user['uuid'], user['tenant_uuid']) for user in users}
        users_cached = {
            (str(u.uuid), str(u.tenant_uuid))
            for u in self._dao.user.list_(tenant_uuids=None)
        }

        users_missing = users - users_cached
        with session_scope():
            for uuid, tenant_uuid in users_missing:
                # Avoid race condition between init tenant and init user
                tenant = self._dao.tenant.find_or_create(tenant_uuid)

                logger.debug('Create user "%s"', uuid)
                user = User(uuid=uuid, tenant=tenant, state='unavailable')
                self._dao.user.create(user)

        users_expired = users_cached - users
        with session_scope():
            for uuid, tenant_uuid in users_expired:
                try:
                    user = self._dao.user.get([tenant_uuid], uuid)
                except UnknownUserException as e:
                    logger.warning(e)
                    continue
                logger.debug('Delete user "%s"', uuid)
                self._dao.user.delete(user)

    def _add_and_remove_lines(self, users):
        lines = {
            (line['id'], user['uuid'], user['tenant_uuid'])
            for user in users
            for line in user['lines']
        }
        lines_cached = {
            (line.id, str(line.user_uuid), str(line.tenant_uuid))
            for line in self._dao.line.list_()
        }

        lines_missing = lines - lines_cached
        with session_scope():
            for id_, user_uuid, tenant_uuid in lines_missing:
                try:
                    user = self._dao.user.get([tenant_uuid], user_uuid)
                except UnknownUserException as e:
                    logger.warning(e)
                    continue
                if self._dao.line.find(id_):
                    logger.warning(
                        'Line "%s" already created. Line multi-users not supported', id_
                    )
                    continue
                line = Line(id=id_)
                logger.debug('Create line "%s"', id_)
                self._dao.user.add_line(user, line)

        lines_expired = lines_cached - lines
        with session_scope():
            for id_, user_uuid, tenant_uuid in lines_expired:
                try:
                    user = self._dao.user.get([tenant_uuid], user_uuid)
                    line = self._dao.line.get(id_)
                except UnknownUserException:
                    logger.debug('Line "%s" already deleted', id_)
                    continue
                logger.debug('Delete line "%s"', id_)
                self._dao.user.remove_session(user, line)

    def _add_missing_endpoints(self, users):
        lines = {
            (line['id'], extract_endpoint_from_line(line))
            for user in users
            for line in user['lines']
        }
        with session_scope():
            for line_id, endpoint_name in lines:
                if not endpoint_name:
                    logger.warning('Line "%s" doesn\'t have name', line_id)
                    continue

                endpoint = self._dao.endpoint.find_by(name=endpoint_name)
                if endpoint:
                    continue

                logger.debug('Create endpoint "%s"', endpoint_name)
                self._dao.endpoint.create(Endpoint(name=endpoint_name))

    def _associate_line_endpoint(self, users):
        lines = {
            (line['id'], extract_endpoint_from_line(line))
            for user in users
            for line in user['lines']
        }
        with session_scope():
            for line_id, endpoint_name in lines:
                try:
                    line = self._dao.line.get(line_id)
                    endpoint = self._dao.endpoint.get_by(name=endpoint_name)
                except (UnknownLineException, UnknownEndpointException):
                    logger.debug(
                        'Unable to associate line "%s" with endpoint "%s"',
                        line_id,
                        endpoint_name,
                    )
                    continue
                logger.debug(
                    'Associate line "%s" with endpoint "%s"', line.id, endpoint.name
                )
                self._dao.line.associate_endpoint(line, endpoint)

    def _update_services_users(self, users):
        with session_scope() as session:
            for confd_user in users:
                try:
                    user = self._dao.user.get(
                        [confd_user['tenant_uuid']], confd_user['uuid']
                    )
                except UnknownUserException as e:
                    logger.warning(e)
                    continue
                do_not_disturb_status = confd_user['services']['dnd']['enabled']
                logger.debug(
                    'Updating user "%s" DND status to "%s"',
                    user.uuid,
                    do_not_disturb_status,
                )
                user.do_not_disturb = do_not_disturb_status
                session.flush()

    def initiate_sessions(self, sessions):
        self._add_and_remove_sessions(sessions)
        self._update_sessions(sessions)

    def _add_and_remove_sessions(self, sessions):
        sessions = {
            (session['uuid'], session['user_uuid'], session['tenant_uuid'])
            for session in sessions
        }
        sessions_cached = {
            (str(session.uuid), str(session.user_uuid), str(session.tenant_uuid))
            for session in self._dao.session.list_()
        }

        sessions_missing = sessions - sessions_cached
        with session_scope():
            for uuid, user_uuid, tenant_uuid in sessions_missing:
                try:
                    user = self._dao.user.get([tenant_uuid], user_uuid)
                except UnknownUserException:
                    logger.debug('Session "%s" has no valid user "%s"', uuid, user_uuid)
                    continue

                logger.debug('Create session "%s" for user "%s"', uuid, user_uuid)
                session = Session(uuid=uuid, user_uuid=user_uuid)
                self._dao.user.add_session(user, session)

        sessions_expired = sessions_cached - sessions
        with session_scope():
            for uuid, user_uuid, tenant_uuid in sessions_expired:
                try:
                    user = self._dao.user.get([tenant_uuid], user_uuid)
                    session = self._dao.session.get(uuid)
                except (UnknownUserException, UnknownSessionException) as e:
                    logger.warning(e)
                    continue

                logger.debug('Delete session "%s" for user "%s"', uuid, user_uuid)
                self._dao.user.remove_session(user, session)

    def _update_sessions(self, sessions):
        with session_scope():
            for session in sessions:
                cached_session = self._dao.session.find(session['uuid'])
                if cached_session and session['mobile'] != cached_session.mobile:
                    cached_session.mobile = session['mobile']
                    self._dao.session.update(cached_session)

    def initiate_refresh_tokens(self, tokens):
        self._add_and_remove_refresh_tokens(tokens)
        self._update_refresh_tokens(tokens)

    def _add_and_remove_refresh_tokens(self, tokens):
        tokens = {
            (token['client_id'], token['user_uuid'], token['tenant_uuid'])
            for token in tokens
        }
        tokens_cached = {
            (token.client_id, str(token.user_uuid), str(token.tenant_uuid))
            for token in self._dao.refresh_token.list_()
        }

        tokens_missing = tokens - tokens_cached
        with session_scope():
            for client_id, user_uuid, tenant_uuid in tokens_missing:
                try:
                    user = self._dao.user.get([tenant_uuid], user_uuid)
                except UnknownUserException:
                    logger.debug(
                        'Refresh token "%s" has no valid user "%s"',
                        client_id,
                        user_uuid,
                    )
                    continue

                logger.debug(
                    'Create refresh token "%s" for user "%s"', client_id, user_uuid
                )
                token = RefreshToken(client_id=client_id, user_uuid=user_uuid)
                self._dao.user.add_refresh_token(user, token)

        tokens_expired = tokens_cached - tokens
        with session_scope():
            for client_id, user_uuid, tenant_uuid in tokens_expired:
                try:
                    user = self._dao.user.get([tenant_uuid], user_uuid)
                    token = self._dao.refresh_token.get(user_uuid, client_id)
                except (UnknownUserException, UnknownRefreshTokenException) as e:
                    logger.warning(e)
                    continue

                logger.debug(
                    'Delete refresh token "%s" for user "%s"', client_id, user_uuid
                )
                self._dao.user.remove_refresh_token(user, token)

    def _update_refresh_tokens(self, tokens):
        with session_scope():
            for token in tokens:
                cached_token = self._dao.refresh_token.find(
                    token['user_uuid'], token['client_id']
                )
                if cached_token and token['mobile'] != cached_token.mobile:
                    cached_token.mobile = token['mobile']
                    self._dao.refresh_token.update(cached_token)

    def initiate_endpoints(self, events):
        with session_scope():
            logger.debug('Delete all endpoints')
            self._dao.endpoint.delete_all()
            for event in events:
                if event.get('Event') != 'DeviceStateChange':
                    continue

                endpoint_name = event['Device']
                if endpoint_name.startswith('Custom:'):
                    continue

                endpoint_args = {
                    'name': endpoint_name,
                    'state': DEVICE_STATE_MAP.get(event['State'], 'unavailable'),
                }
                logger.debug(
                    'Create endpoint "%s" with state "%s"',
                    endpoint_args['name'],
                    endpoint_args['state'],
                )
                self._dao.endpoint.create(Endpoint(**endpoint_args))

    def initiate_channels(self, events):
        with session_scope():
            logger.debug('Delete all channels')
            self._dao.channel.delete_all()
            for event in events:
                if event.get('Event') != 'CoreShowChannel':
                    continue

                channel_name = event['Channel']
                endpoint_name = extract_endpoint_from_channel(channel_name)
                line = self._dao.line.find_by(endpoint_name=endpoint_name)
                if not line:
                    logger.debug(
                        'Unknown line with endpoint "%s" for channel "%s"',
                        endpoint_name,
                        channel_name,
                    )
                    continue

                state = CHANNEL_STATE_MAP.get(event['ChannelStateDesc'], 'undefined')
                if event['ChanVariable'].get('XIVO_ON_HOLD') == '1':
                    state = 'holding'

                channel_args = {
                    'name': channel_name,
                    'state': state,
                }
                logger.debug(
                    'Create channel "%s" with state "%s"',
                    channel_args['name'],
                    channel_args['state'],
                )
                channel = Channel(**channel_args)
                self._dao.line.add_channel(line, channel)
