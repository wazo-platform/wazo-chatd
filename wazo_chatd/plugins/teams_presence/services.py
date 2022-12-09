# Copyright 2022-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import json

from base64 import urlsafe_b64decode
from requests.exceptions import HTTPError
from typing import Dict

from wazo_auth_client import Client as AuthClient
from wazo_chatd.asyncio_ import CoreAsyncio
from wazo_chatd.database.queries import DAO
from wazo_chatd.plugins.presences.services import PresenceService
from wazo_confd_client import Client as ConfdClient

from .log import make_logger
from .notifier import TeamsNotifier
from .subscriptions import SubscriptionRenewer


logger = make_logger(__name__)
PRESENCES_MAP = {
    'Available': 'available',
    'AvailableIdle': 'available',
    'Away': 'away',
    'BeRightBack': 'away',
    'Busy': 'unavailable',
    'BusyIdle': 'unavailable',
    'DoNotDisturb': 'unavailable',
    'Offline': 'invisible',
    'PresenceUnknown': 'invisible',
}


class TeamsService:
    def __init__(
        self,
        aio: CoreAsyncio,
        auth_client: AuthClient,
        confd_client: ConfdClient,
        config: Dict,
        dao: DAO,
        notifier: TeamsNotifier,
        presence_service: PresenceService,
    ):
        self.aio = aio
        self.auth = auth_client
        self.confd = confd_client
        self.config = config
        self.dao = dao
        self.notifier = notifier
        self.presence_service = presence_service
        self._synchronizers: Dict[str, SubscriptionRenewer] = {}

    async def create_subscription(self, user_uuid: str):
        url = self.config['teams_presence']['microsoft_graph_url']
        try:
            user_config = await self._fetch_configuration(user_uuid)
        except (ValueError, HTTPError):
            logger.error('unable to fetch configuration for user `%s`', user_uuid)
            return

        synchronizer = SubscriptionRenewer(url, user_config, self.notifier)
        await synchronizer.start()

        self._synchronizers[user_uuid] = synchronizer

    async def delete_subscription(self, user_uuid: str):
        synchronizer = self._synchronizers.pop(user_uuid, None)
        if not synchronizer:
            return

        await synchronizer.stop()

    def initialize(self):
        self.aio.schedule_coroutine(self._initialize())

    def is_connected(self, user_uuid: str):
        return user_uuid in self._synchronizers

    def update_presence(self, payload: Dict, user_uuid: str):
        for subscription in payload['data']:
            if not self._synchronizers.get(user_uuid):
                logger.error(
                    'received presence update but user `%s` has no active subscription, discarding',
                    user_uuid,
                )
                continue

            tenant_uuids = [self._synchronizers[user_uuid].tenant_uuid]
            presence = subscription['resource_data']
            state = PRESENCES_MAP.get(presence['availability'])
            dnd = state == 'unavailable'
            user = self.presence_service.get(tenant_uuids, user_uuid)

            user.state = state
            user.do_not_disturb = dnd
            endpoint_state = 'unavailable' if state == 'invisible' else 'available'
            for line in user.lines:
                line.endpoint_state = endpoint_state

            logger.debug('updating `%s` presence to %s', user_uuid, state)
            self.presence_service.update(user)
            self.aio.schedule_coroutine(self._update_confd_dnd(user_uuid, dnd))

    def _decode_jwt(self, token):
        payload = token.split('.')[1]
        remaining = len(payload) % 4
        if remaining == 2:
            payload = ''.join([payload, '=='])
        elif remaining == 1:
            payload = ''.join([payload, '='])

        decoded = json.loads(urlsafe_b64decode(payload))
        return {
            'tenant_id': decoded['tid'],
            'app_id': decoded['appid'],
            'user_id': decoded['oid'],
        }

    async def _initialize(self):
        try:
            results = await self.aio.execute(
                self.auth.external.list_connected_users, 'microsoft', recurse=True
            )
        except HTTPError:
            logger.exception('unable to fetch connected user list')
            raise

        if not results['items']:
            logger.debug('no connected users found, nothing to initialize...')
            return

        logger.debug(
            'found %d connected users, managing subscriptions...', len(results['items'])
        )

        for user in results['items']:
            try:
                await self.create_subscription(user['uuid'])
            except Exception:
                logger.exception('hello')

    async def _fetch_configuration(self, user_uuid) -> Dict:
        fetch = self.aio.execute

        users = self.dao.user.list_(None, uuids=[user_uuid])
        if not users:
            raise ValueError(f'unable to retrieve user `{user_uuid}`')
        tenant_uuid = str(users[0].tenant_uuid)

        token, domains = await asyncio.gather(
            fetch(self.auth.external.get, 'microsoft', user_uuid, tenant_uuid),
            fetch(self.confd.ingress_http.list, tenant_uuid=tenant_uuid),
        )
        domains = [domain['uri'] for domain in domains['items'] if 'uri' in domain]
        return {
            'domain': domains[-1],
            'microsoft': self._decode_jwt(token['access_token']),
            'tenant_uuid': tenant_uuid,
            'token': token['access_token'],
            'user_uuid': user_uuid,
        }

    async def _update_confd_dnd(self, user_uuid, state):
        result = await self.aio.execute(self.confd.users(user_uuid).get_service, 'dnd')
        if result['enabled'] != state:
            await self.aio.execute(
                self.confd.users(user_uuid).update_service, 'dnd', {'enabled': state}
            )