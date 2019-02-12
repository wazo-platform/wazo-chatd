# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from wazo_chatd.database.models import (
    Line,
    User,
    Session,
    Tenant,
)
from wazo_chatd.database.helpers import session_scope
from wazo_chatd.exceptions import (
    UnknownSessionException,
    UnknownUserException,
)

logger = logging.getLogger(__name__)


class Initiator:

    def __init__(self, tenant_dao, user_dao, session_dao, line_dao, auth):
        self._tenant_dao = tenant_dao
        self._user_dao = user_dao
        self._session_dao = session_dao
        self._line_dao = line_dao
        self._auth = auth
        self._token = None

    @property
    def token(self):
        if not self._token:
            self._token = self._auth.token.new(expiration=120)['token']
        return self._token

    def initiate_tenants(self):
        self._auth.set_token(self.token)
        tenants = self._auth.tenants.list()['items']

        tenants = set(tenant['uuid'] for tenant in tenants)
        tenants_cached = set(tenant.uuid for tenant in self._tenant_dao.list_())

        tenants_missing = tenants - tenants_cached
        with session_scope():
            for uuid in tenants_missing:
                logger.debug('Creating tenant with uuid: %s', uuid)
                tenant = Tenant(uuid=uuid)
                self._tenant_dao.create(tenant)

        tenants_expired = tenants_cached - tenants
        with session_scope():
            for uuid in tenants_expired:
                logger.debug('Deleting tenant with uuid: %s', uuid)
                tenant = self._tenant_dao.get(uuid)
                self._tenant_dao.delete(tenant)

    def initiate_users(self, confd):
        confd.set_token(self.token)
        users = confd.users.list(recurse=True)['items']
        self._add_and_remove_users(confd, users)
        self._add_and_remove_lines(confd, users)
        self._update_lines(confd, users)

    def _add_and_remove_users(self, confd, users):
        users = set((user['uuid'], user['tenant_uuid']) for user in users)
        users_cached = set((u.uuid, u.tenant_uuid) for u in self._user_dao.list_(tenant_uuids=None))

        users_missing = users - users_cached
        with session_scope():
            for uuid, tenant_uuid in users_missing:
                # Avoid race condition between init tenant and init user
                tenant = self._tenant_dao.find_or_create(tenant_uuid)

                logger.debug('Creating user with uuid: %s', uuid)
                user = User(uuid=uuid, tenant=tenant, state='unavailable')
                self._user_dao.create(user)

        users_expired = users_cached - users
        with session_scope():
            for uuid, tenant_uuid in users_expired:
                logger.debug('Deleting user with uuid: %s', uuid)
                try:
                    user = self._user_dao.get([tenant_uuid], uuid)
                except UnknownUserException as e:
                    logger.warning('%s', e)
                    continue
                self._user_dao.delete(user)

    def _add_and_remove_lines(self, confd, users):
        lines = set((line['id'], user['uuid'], user['tenant_uuid']) for user in users for line in user['lines'])
        lines_cached = set((line.id, line.user_uuid, line.tenant_uuid) for line in self._line_dao.list_())

        lines_missing = lines - lines_cached
        with session_scope():
            for id_, user_uuid, tenant_uuid in lines_missing:
                logger.debug('Creating line with id: %s' % id_)
                user = self._user_dao.get([tenant_uuid], user_uuid)
                line = Line(id=id_, state='unavailable')
                self._user_dao.add_line(user, line)

        lines_expired = lines_cached - lines
        with session_scope():
            for id_, user_uuid, tenant_uuid in lines_expired:
                logger.debug('Deleting line with id: %s' % id_)
                try:
                    user = self._user_dao.get([tenant_uuid], user_uuid)
                    line = self._line_dao.get(id_)
                except UnknownUserException:
                    logger.debug('Line already deleted: id: %s, user_uuid: %s' % (id_, user_uuid))
                    continue
                self._user_dao.remove_session(user, line)

    def _update_lines(self, confd, users):
        lines_info = [{'id': line['id'], 'device_name': self._extract_device_name(line)}
                      for user in users for line in user['lines']]
        with session_scope():
            for line_info in lines_info:
                logger.debug('Updating line with id: %s' % line_info['id'])
                line = self._line_dao.get(line_info['id'])
                line.device_name = line_info['device_name']
                self._line_dao.update(line)

    def _extract_device_name(self, line):
        if line.get('endpoint_sip'):
            return 'PJSIP/{}'.format(line['name'])
        elif line.get('endpoint_sccp'):
            return 'SCCP/{}'.format(line['name'])
        elif line.get('endpoint_custom'):
            return line['endpoint_custom']['interface']

    def initiate_sessions(self):
        self._auth.set_token(self.token)
        sessions = self._auth.sessions.list(recurse=True)['items']

        sessions = set(
            (session['uuid'], session['user_uuid'], session['tenant_uuid'])
            for session in sessions
        )
        sessions_cached = set(
            (session.uuid, session.user_uuid, session.tenant_uuid)
            for session in self._session_dao.list_()
        )

        sessions_missing = sessions - sessions_cached
        with session_scope():
            for uuid, user_uuid, tenant_uuid in sessions_missing:
                logger.debug('Creating session with uuid: %s, user_uuid %s', uuid, user_uuid)
                try:
                    user = self._user_dao.get([tenant_uuid], user_uuid)
                except UnknownUserException:
                    logger.debug('Session has no valid user associated:' +
                                 'session_uuid %s, user_uuid %s', uuid, user_uuid)
                    continue

                session = Session(uuid=uuid, user_uuid=user_uuid)
                self._user_dao.add_session(user, session)

        sessions_expired = sessions_cached - sessions
        with session_scope():
            for uuid, user_uuid, tenant_uuid in sessions_expired:
                logger.debug('Deleting session with uuid: %s, user_uuid %s', uuid, user_uuid)
                try:
                    user = self._user_dao.get([tenant_uuid], user_uuid)
                    session = self._session_dao.get(uuid)
                except (UnknownUserException, UnknownSessionException) as e:
                    logger.warning('%s', e)
                    continue

                self._user_dao.remove_session(user, session)
