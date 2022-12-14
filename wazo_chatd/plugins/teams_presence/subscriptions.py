# Copyright 2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import asyncio
import iso8601
import requests

from datetime import datetime, timezone, timedelta
from functools import partial
from requests.exceptions import HTTPError
from typing import Dict

from .log import make_logger
from .notifier import TeamsNotifier


logger = make_logger(__name__)

DEFAULT_EXPIRATION = 3600  # 1 hour
DEFAULT_LEEWAY = 600  # 10 mins


class _HTTPHelper:
    def __init__(self, base_url: str, headers: Dict[str, str] = None):
        self.base_url = base_url
        self.headers = headers

    @classmethod
    async def execute(cls, method, *args, **kwargs):
        loop = asyncio.get_running_loop()
        fn = partial(method, *args, **kwargs)
        return await loop.run_in_executor(None, fn)

    def make_url(self, *path):
        return '/'.join([self.base_url, *path])

    async def create(self, *path: str, json: Dict = None):
        url = self.make_url(*path)
        return await self.execute(requests.post, url, json=json, headers=self.headers)

    async def delete(self, *path: str, json: Dict = None):
        url = self.make_url(*path)
        return await self.execute(requests.delete, url, json=json, headers=self.headers)

    async def read(self, *path: str):
        url = self.make_url(*path)
        return await self.execute(requests.get, url, headers=self.headers)

    async def update(self, *path: str, json: Dict = None):
        url = self.make_url(*path)
        return await self.execute(requests.patch, url, json=json, headers=self.headers)


class SubscriptionRenewer:
    def __init__(self, base_url: str, config: Dict, notifier: TeamsNotifier):
        self._config: Dict[str, str] = config
        self._expiration = 0
        self._id = None
        self._notifier = notifier
        self._task: asyncio.Task = None
        self._token: str = config['token']
        self._http = _HTTPHelper(base_url, self.headers)

    @property
    def headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self._token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

    @property
    def tenant_uuid(self):
        return self._config['tenant_uuid']

    def remaining_time(self) -> int:
        if not self._expiration:
            return 0
        now = datetime.now(timezone.utc)
        return int((self._expiration - now).total_seconds())

    async def start(self):
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._task.cancel()
        await self._task

    def _build_notification_url(self) -> str:
        user_uuid = self._config['user_uuid']
        domain = self._config['domain']
        if '://' not in domain:
            domain = f'https://{domain}'
        return f'{domain}/api/chatd/1.0/users/{user_uuid}/teams/presence'

    async def _create_subscription(self, *, expiry=DEFAULT_EXPIRATION):
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expiry)
        user_id = self._config['microsoft']['user_id']

        payload = {
            'changeType': 'updated',
            'resource': f'/communications/presences/{user_id}',
            'notificationUrl': self._build_notification_url(),
            'expirationDateTime': expires_at.isoformat().replace('+00:00', 'Z'),
            'clientState': 'wazo-teams-integration',
        }

        response = await self._http.create('subscriptions', json=payload)
        if response.status_code == 409:
            try:
                await self._find_subscription()
            except (HTTPError, ValueError):
                raise

        if response.status_code == 400:
            logger.error(
                'failed to create subscription (teams was unable to communicate with the stack)'
            )
        response.raise_for_status()

        subscription = response.json()
        self._id = subscription['id']
        self._expiration = iso8601.parse_date(subscription['expirationDateTime'])
        logger.debug(
            'created subscription `%s` (expires in %d second(s))',
            self._id,
            self.remaining_time(),
        )

    async def _delete_subscription(self):
        if not self._id:
            return
        response = await self._http.delete('subscriptions', self._id)
        response.raise_for_status()
        logger.debug('removed subscription `%s`', self._id)

    async def _find_subscription(self):
        user_uuid = self._config['user_uuid']
        user_id = self._config['microsoft']['user_id']
        expected_resource = f'/communication/presences/{user_id}'

        response = await self._http.read('subscriptions')
        response.raise_for_status()

        for subscription in response.json()['value']:
            if (
                subscription['resource'] == expected_resource
                and subscription['changeType'] == 'updated'
            ):
                self._id = subscription['id']
                self._expiration = iso8601.parse_date(
                    subscription['expirationDateTime']
                )
                logger.debug(
                    'found subscription `%s` (expires in %d second(s)))',
                    self._id,
                    self.remaining_time(),
                )
                return
        logger.debug('no compatible subscription found for user `%s`', user_uuid)
        raise ValueError()

    async def _renew_subscription(self, *, expiry=DEFAULT_EXPIRATION):
        if not self._id:
            raise ValueError('must have a valid subscription to renew')

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expiry)
        payload = {'expirationDateTime': expires_at.isoformat().replace('+00:00', 'Z')}

        response = await self._http.update('subscriptions', self._id, json=payload)
        response.raise_for_status()

        subscription = response.json()
        self._expiration = iso8601.parse_date(subscription['expirationDateTime'])
        logger.debug(
            'renewed subscription `%s` (expires in %d second(s))',
            self._id,
            self.remaining_time(),
        )

    async def _run(self, *, expiry=DEFAULT_EXPIRATION, leeway=DEFAULT_LEEWAY):
        user_uuid = self._config['user_uuid']
        tenant_uuid = self._config['tenant_uuid']

        try:
            await self._create_subscription(expiry=expiry)
        except (ValueError, HTTPError):
            logger.error('unable to create a subscription for user `%s`', user_uuid)
            return
        else:
            logger.debug('subscription renewer started for user `%s`', user_uuid)
            await self._notifier.subscribed(tenant_uuid, user_uuid)

        while True:
            duration = self.remaining_time() - leeway
            try:
                if duration > 0:
                    await asyncio.sleep(duration)
                await self._renew_subscription(expiry=expiry)
            except HTTPError:
                logger.error('failed to renew subscription for user `%s`', user_uuid)
                break
            except asyncio.CancelledError:
                break
        await self._delete_subscription()
        logger.debug('subscription renewer stopped for user `%s`', user_uuid)
        await self._notifier.unsubscribed(tenant_uuid, user_uuid)
