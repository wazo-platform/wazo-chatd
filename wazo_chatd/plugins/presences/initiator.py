# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import threading
import time
from enum import Enum, auto
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


class Resource(Enum):
    CHANNEL = auto()
    DEVICE = auto()
    REFRESH_TOKEN = auto()
    SESSION = auto()
    TENANT = auto()
    USER = auto()


class Stage(Enum):
    FETCHED = auto()


class MilestoneTracker:
    def __init__(self):
        self._milestones = set()
        self._lock = threading.Lock()

    def mark(self, resource, stage):
        with self._lock:
            self._milestones.add((resource, stage))

    def has_passed(self, resource, stage):
        with self._lock:
            return (resource, stage) in self._milestones

    def reset(self):
        with self._lock:
            self._milestones.clear()


def extract_endpoint_from_channel(channel_name):
    endpoint_name = '-'.join(channel_name.split('-')[:-1])
    if not endpoint_name:
        logger.debug('Invalid endpoint from channel "%s"', channel_name)
        return
    return endpoint_name


def _endpoint_name_for_protocol(protocol, line_name):
    match protocol:
        case 'sip':
            return f'PJSIP/{line_name}'
        case 'sccp':
            return f'SCCP/{line_name}'
        case 'custom':
            return line_name
        case _:
            return None


def extract_endpoint_from_line_presence_view(line):
    if not line['name']:
        return
    return _endpoint_name_for_protocol(line.get('protocol'), line['name'])


def extract_endpoint_from_line(line):
    if not line['name']:
        return
    if line.get('endpoint_sip'):
        return _endpoint_name_for_protocol('sip', line['name'])
    if line.get('endpoint_sccp'):
        return _endpoint_name_for_protocol('sccp', line['name'])
    if line.get('endpoint_custom'):
        return _endpoint_name_for_protocol('custom', line['name'])


class Initiator:
    def __init__(self, dao, auth, amid, confd, token_expiration):
        self._dao = dao
        self._auth = auth
        self._amid = amid
        self._confd = confd
        self._token_expiration = token_expiration
        self._is_initialized = threading.Event()
        self._in_progress = threading.Event()
        self.post_hooks = []
        self._milestone_tracker = MilestoneTracker()

    def provide_status(self, status):
        status['presence_initialization']['status'] = (
            Status.ok if self.is_initialized() else Status.fail
        )

    def is_initialized(self):
        return self._is_initialized.is_set()

    def in_progress(self):
        return self._in_progress.is_set()

    def _paginate_proxy(self, callback, limit=1000, **list_params):
        callback = partial(callback, recurse=True, limit=limit, **list_params)
        result = callback(limit=limit, offset=0)
        total = result['total']
        items = result['items']
        offset = len(items)
        while offset < total:
            new_items = callback(offset=offset)['items']
            items.extend(new_items)
            offset += len(new_items)
        if len(items) != total:
            logger.warning('Fetched %d items but total was %d', len(items), total)
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

    def has_fetched(self, resource):
        return self._milestone_tracker.has_passed(resource, Stage.FETCHED)

    def initiate(self):
        start = time.monotonic()
        self._milestone_tracker.reset()
        self._in_progress.set()

        token = self._auth.token.new(expiration=self._token_expiration)['token']
        self._auth.set_token(token)
        self._amid.set_token(token)
        self._confd.set_token(token)

        logger.debug('Fetching tenants...')
        tenants = self._paginate_proxy(self._auth.tenants.list, limit=10000)['items']
        self._milestone_tracker.mark(Resource.TENANT, Stage.FETCHED)

        logger.debug('Fetching users...')
        users = self._paginate_proxy(
            self._confd.users.list, limit=1000, view='line_presence'
        )['items']
        self._milestone_tracker.mark(Resource.USER, Stage.FETCHED)

        logger.debug('Fetching sesions...')
        sessions = self._paginate_proxy(self._auth.sessions.list, limit=10000)['items']
        self._milestone_tracker.mark(Resource.SESSION, Stage.FETCHED)

        logger.debug('Fetching refresh tokens...')
        refresh_tokens = self._paginate_proxy(
            self._auth.refresh_tokens.list,
            limit=10000,
        )['items']
        self._milestone_tracker.mark(Resource.REFRESH_TOKEN, Stage.FETCHED)

        logger.debug('Fetching device states...')
        endpoint_events = self._amid.action('DeviceStateList')
        self._milestone_tracker.mark(Resource.DEVICE, Stage.FETCHED)

        logger.debug('Fetching channels...')
        channel_events = self._amid.action('CoreShowChannels')
        self._milestone_tracker.mark(Resource.CHANNEL, Stage.FETCHED)

        logger.debug('Fetching data done!')

        self.initiate_endpoints(endpoint_events)
        self.initiate_tenants(tenants)
        self.initiate_users(users)
        self.initiate_sessions(sessions)
        self.initiate_refresh_tokens(refresh_tokens)
        self.initiate_channels(channel_events)
        self.execute_post_hooks()
        self._in_progress.clear()
        self._is_initialized.set()
        logger.info(
            'Presence initialization completed in %.2fs', time.monotonic() - start
        )

    def initiate_tenants(self, tenants):
        tenants = {tenant['uuid'] for tenant in tenants}
        tenants_cached = {str(tenant.uuid) for tenant in self._dao.tenant.list_()}

        tenants_missing = tenants - tenants_cached
        tenants_expired = tenants_cached - tenants

        with session_scope():
            new_tenants = []
            for uuid in tenants_missing:
                logger.debug('Create tenant "%s"', uuid)
                new_tenants.append(Tenant(uuid=uuid))
            self._dao.tenant.create_all(new_tenants)

            for uuid in tenants_expired:
                logger.debug('Delete tenant "%s"', uuid)
            self._dao.tenant.delete_by_uuids(list(tenants_expired))

    def initiate_users(self, users):
        self._add_and_remove_users(users)
        self._add_and_remove_lines(users)
        self._add_missing_endpoints(users)  # disconnected SCCP endpoints are missing
        self._associate_line_endpoint(users)
        self._update_services_users(users)

    def _add_and_remove_users(self, users):
        users = {(user['uuid'], user['tenant_uuid']) for user in users}
        users_cached = {
            (str(uuid), str(tenant_uuid))
            for uuid, tenant_uuid in self._dao.user.list_uuids_with_tenant_uuids()
        }

        users_missing = users - users_cached
        users_expired = users_cached - users

        with session_scope():
            # Avoid race condition between init tenant and init user
            existing_tenants = self._dao.tenant.list_uuids()
            missing_tenants = {t for _, t in users_missing} - existing_tenants
            self._dao.tenant.create_all([Tenant(uuid=t) for t in missing_tenants])

            new_users = []
            for uuid, tenant_uuid in users_missing:
                logger.debug('Create user "%s"', uuid)
                new_users.append(
                    User(uuid=uuid, tenant_uuid=tenant_uuid, state='unavailable')
                )
            self._dao.user.create_all(new_users)

            expired_uuids = []
            for uuid, tenant_uuid in users_expired:
                logger.debug('Delete user "%s"', uuid)
                expired_uuids.append(uuid)
            self._dao.user.delete_by_uuids(expired_uuids)

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
        lines_expired = lines_cached - lines
        existing_line_ids = {id_ for id_, _, _ in lines_cached}

        with session_scope():
            user_uuids = self._dao.user.list_uuids()
            new_lines = []
            new_line_ids = set()
            for id_, user_uuid, tenant_uuid in lines_missing:
                if user_uuid not in user_uuids:
                    logger.warning('Line "%s" has no valid user "%s"', id_, user_uuid)
                    continue
                if id_ in existing_line_ids or id_ in new_line_ids:
                    logger.warning(
                        'Line "%s" already created. Line multi-users not supported', id_
                    )
                    continue
                logger.debug('Create line "%s"', id_)
                new_line_ids.add(id_)
                new_lines.append(Line(id=id_, user_uuid=user_uuid))
            self._dao.line.create_all(new_lines)

            expired_ids = []
            for id_, user_uuid, tenant_uuid in lines_expired:
                logger.debug('Delete line "%s"', id_)
                expired_ids.append(id_)
            self._dao.line.delete_by_ids(expired_ids)

    def _add_missing_endpoints(self, users):
        endpoint_names = set()
        for user in users:
            for line in user['lines']:
                endpoint_name = extract_endpoint_from_line_presence_view(line)
                if not endpoint_name:
                    logger.warning('Line "%s" doesn\'t have name', line['id'])
                    continue

                endpoint_names.add(endpoint_name)

        with session_scope():
            existing = self._dao.endpoint.list_names()
            missing = []
            for name in endpoint_names - existing:
                logger.debug('Create endpoint "%s"', name)
                missing.append(Endpoint(name=name))
            self._dao.endpoint.create_all(missing)

    def _associate_line_endpoint(self, users):
        desired = {}
        for user in users:
            for line in user['lines']:
                endpoint_name = extract_endpoint_from_line_presence_view(line)
                if endpoint_name:
                    desired[line['id']] = endpoint_name

        with session_scope():
            cached = {line.id: line.endpoint_name for line in self._dao.line.list_()}
            associations = []
            for line_id, endpoint_name in desired.items():
                if cached.get(line_id) == endpoint_name:
                    continue
                logger.debug(
                    'Associate line "%s" with endpoint "%s"', line_id, endpoint_name
                )
                associations.append({'id': line_id, 'endpoint_name': endpoint_name})
            self._dao.line.associate_endpoints(associations)

    def _update_services_users(self, users):
        desired = {user['uuid']: user['services']['dnd']['enabled'] for user in users}

        with session_scope():
            cached = self._dao.user.list_dnd()
            changed = []
            for uuid, do_not_disturb in desired.items():
                if cached.get(uuid) == do_not_disturb:
                    continue
                logger.debug(
                    'Updating user "%s" DND status to "%s"', uuid, do_not_disturb
                )
                changed.append((uuid, do_not_disturb))
            self._dao.user.update_dnd(changed)

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
        sessions_expired = sessions_cached - sessions

        with session_scope():
            user_uuids = self._dao.user.list_uuids()
            new_sessions = []
            for uuid, user_uuid, tenant_uuid in sessions_missing:
                if user_uuid not in user_uuids:
                    logger.debug('Session "%s" has no valid user "%s"', uuid, user_uuid)
                    continue

                logger.debug('Create session "%s" for user "%s"', uuid, user_uuid)
                new_sessions.append(Session(uuid=uuid, user_uuid=user_uuid))
            self._dao.session.create_all(new_sessions)

            expired_uuids = []
            for uuid, user_uuid, tenant_uuid in sessions_expired:
                logger.debug('Delete session "%s" for user "%s"', uuid, user_uuid)
                expired_uuids.append(uuid)
            self._dao.session.delete_by_uuids(expired_uuids)

    def _update_sessions(self, sessions):
        sessions_by_uuid = {session['uuid']: session for session in sessions}
        with session_scope():
            updates = []
            for cached_session in self._dao.session.list_():
                session = sessions_by_uuid.get(str(cached_session.uuid))
                if session is not None and session['mobile'] != cached_session.mobile:
                    updates.append(
                        {'uuid': cached_session.uuid, 'mobile': session['mobile']}
                    )
            self._dao.session.update_all(updates)

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
        tokens_expired = tokens_cached - tokens

        with session_scope():
            user_uuids = self._dao.user.list_uuids()
            new_tokens = []
            for client_id, user_uuid, tenant_uuid in tokens_missing:
                if user_uuid not in user_uuids:
                    logger.debug(
                        'Refresh token "%s" has no valid user "%s"',
                        client_id,
                        user_uuid,
                    )
                    continue

                logger.debug(
                    'Create refresh token "%s" for user "%s"', client_id, user_uuid
                )
                new_tokens.append(
                    RefreshToken(client_id=client_id, user_uuid=user_uuid)
                )
            self._dao.refresh_token.create_all(new_tokens)

            expired_keys = []
            for client_id, user_uuid, tenant_uuid in tokens_expired:
                logger.debug(
                    'Delete refresh token "%s" for user "%s"', client_id, user_uuid
                )
                expired_keys.append((client_id, user_uuid))
            self._dao.refresh_token.delete_by_keys(expired_keys)

    def _update_refresh_tokens(self, tokens):
        tokens_by_key = {
            (token['user_uuid'], token['client_id']): token for token in tokens
        }
        with session_scope():
            updates = []
            for cached_token in self._dao.refresh_token.list_():
                key = (str(cached_token.user_uuid), cached_token.client_id)
                token = tokens_by_key.get(key)
                if token is not None and token['mobile'] != cached_token.mobile:
                    updates.append(
                        {
                            'client_id': cached_token.client_id,
                            'user_uuid': cached_token.user_uuid,
                            'mobile': token['mobile'],
                        }
                    )
            self._dao.refresh_token.update_all(updates)

    def initiate_endpoints(self, events):
        endpoints = {}
        for event in events:
            if event.get('Event') != 'DeviceStateChange':
                continue

            endpoint_name = event['Device']
            if endpoint_name.startswith('Custom:'):
                continue

            state = DEVICE_STATE_MAP.get(event['State'], 'unavailable')
            logger.debug('Create endpoint "%s" with state "%s"', endpoint_name, state)
            endpoints[endpoint_name] = Endpoint(name=endpoint_name, state=state)

        with session_scope():
            logger.debug('Delete all endpoints')
            self._dao.endpoint.delete_all()
            self._dao.endpoint.create_all(list(endpoints.values()))

    def initiate_channels(self, events):
        with session_scope():
            logger.debug('Delete all channels')
            self._dao.channel.delete_all()

            line_id_by_endpoint = {
                line.endpoint_name: line.id
                for line in self._dao.line.list_()
                if line.endpoint_name
            }

            channels = {}
            for event in events:
                if event.get('Event') != 'CoreShowChannel':
                    continue

                channel_name = event['Channel']
                endpoint_name = extract_endpoint_from_channel(channel_name)
                line_id = line_id_by_endpoint.get(endpoint_name)
                if line_id is None:
                    logger.debug(
                        'Unknown line with endpoint "%s" for channel "%s"',
                        endpoint_name,
                        channel_name,
                    )
                    continue

                state = CHANNEL_STATE_MAP.get(event['ChannelStateDesc'], 'undefined')
                if event['ChanVariable'].get('XIVO_ON_HOLD') == '1':
                    state = 'holding'

                logger.debug('Create channel "%s" with state "%s"', channel_name, state)
                channels[channel_name] = Channel(
                    name=channel_name, state=state, line_id=line_id
                )

            self._dao.channel.create_all(list(channels.values()))
