# Copyright 2022-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import asyncio
import json

from base64 import urlsafe_b64decode
from requests.exceptions import HTTPError

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
        config: dict,
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

        self._synchronizers: dict[str, SubscriptionRenewer] = {}
        self._db_lock = asyncio.locks.Lock(loop=aio.loop)

    async def create_subscription(self, user_uuid: str):
        url = self.config['teams_presence']['microsoft_graph_url']
        try:
            user_config = await self._fetch_configuration(user_uuid)
        except (ValueError, HTTPError) as exc:
            logger.error(
                'unable to fetch configuration for user `%s` (%s)', user_uuid, exc
            )
            return

        if user_uuid in self._synchronizers:
            raise ValueError(f'user `{user_uuid}` is already being synchronized')

        self._synchronizers[user_uuid] = synchronizer = SubscriptionRenewer(
            self.auth, url, user_config, self.notifier
        )
        synchronizer.start()

    async def delete_subscription(self, user_uuid: str):
        synchronizer = self._synchronizers.pop(user_uuid, None)
        if not synchronizer:
            return

        synchronizer.stop()

    def initialize(self):
        self.aio.schedule_coroutine(self._initialize())

    def is_connected(self, user_uuid: str):
        return user_uuid in self._synchronizers

    def update_presence(self, payload: dict, user_uuid: str):
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

            if state == 'invisible':
                logger.debug(
                    'discarding offline presence update for user `%s`', user_uuid
                )
                return

            dnd = state == 'unavailable'
            user = self.presence_service.get(tenant_uuids, user_uuid)

            user.state = state
            user.do_not_disturb = dnd

            logger.debug('updating `%s` presence to %s', user_uuid, state)
            self.presence_service.update(user)
            self.aio.schedule_coroutine(self._update_confd_dnd(user_uuid, dnd))

    def _decode_jwt(self, token):
        payload = token.split('.')[1]

        decoded = json.loads(urlsafe_b64decode(payload + '==='))
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

        asyncio.gather(
            *[self.create_subscription(user['uuid']) for user in results['items']]
        )

    async def _fetch_configuration(self, user_uuid) -> dict:
        fetch = self._retry_fetch

        async with self._db_lock:
            users = self.dao.user.list_(None, uuids=[user_uuid])
        if not users:
            raise ValueError(f'unable to retrieve user `{user_uuid}`')
        tenant_uuid = str(users[0].tenant_uuid)

        token, domains = await asyncio.gather(
            fetch(self.auth.external.get, 'microsoft', user_uuid, tenant_uuid),
            fetch(self.confd.ingress_http.list, tenant_uuid=tenant_uuid),
        )

        if not domains['items']:
            raise ValueError('no domain configured for this tenant')

        domains = [domain['uri'] for domain in domains['items'] if 'uri' in domain]
        return {
            'domain': domains[-1],
            'microsoft': self._decode_jwt(token['access_token']),
            'tenant_uuid': tenant_uuid,
            'token': token['access_token'],
            'user_uuid': user_uuid,
        }

    async def _retry_fetch(self, fun, *args, **kwargs):
        fetch = self.aio.execute
        retries = 3

        for _ in range(retries + 1):
            try:
                return await fetch(fun, *args, **kwargs)
            except HTTPError as exc:
                await asyncio.sleep(1)
                last_exc = exc
        raise last_exc

    async def _update_confd_dnd(self, user_uuid, state):
        result = await self.aio.execute(self.confd.users(user_uuid).get_service, 'dnd')
        if result['enabled'] != state:
            await self.aio.execute(
                self.confd.users(user_uuid).update_service, 'dnd', {'enabled': state}
            )
