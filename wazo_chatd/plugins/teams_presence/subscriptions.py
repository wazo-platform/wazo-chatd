# Copyright 2022-2024 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from functools import partial

import iso8601
import requests
from requests.exceptions import HTTPError
from wazo_auth_client import Client as AuthClient

from .log import make_logger
from .notifier import TeamsNotifier

logger = make_logger(__name__)

DEFAULT_EXPIRATION = 3600  # 1 hour
DEFAULT_LEEWAY = 600  # 10 mins


class _HTTPHelper:
    def __init__(self, auth_client: AuthClient, base_url: str, config: dict[str, str]):
        self._auth = auth_client
        self._base_url = base_url
        self._config = config
        self._token = config['token']

    def _headers(self):
        return {
            'Authorization': f'Bearer {self._token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

    async def _refresh_token(self):
        loop = asyncio.get_running_loop()
        user_uuid = self._config['user_uuid']
        tenant_uuid = self._config['tenant_uuid']
        fn = partial(self._auth.external.get, 'microsoft', user_uuid, tenant_uuid)
        try:
            data = await loop.run_in_executor(None, fn)
        except HTTPError as exc:
            logger.error(
                'failed to refresh user\'s `%s` Microsoft token: %s', user_uuid, exc
            )
        else:
            logger.debug('renewed Microsoft access token for user `%s`', user_uuid)
            self._token = data['access_token']

    async def _dispatch(self, method, *args, **kwargs):
        loop = asyncio.get_running_loop()
        kwargs.update(headers=self._headers())
        fn = partial(method, *args, **kwargs)
        return await loop.run_in_executor(None, fn)

    async def _execute_with_retry(self, method, *args, **kwargs):
        response = await self._dispatch(method, *args, **kwargs)
        if response.status_code == 401:
            await self._refresh_token()
            return await self._dispatch(method, *args, **kwargs)
        return response

    def _make_url(self, *path):
        return '/'.join([self._base_url, *path])

    async def create(self, *path: str, json: dict | None = None):
        url = self._make_url(*path)
        return await self._execute_with_retry(requests.post, url, json=json)

    async def delete(self, *path: str, json: dict | None = None):
        url = self._make_url(*path)
        return await self._execute_with_retry(requests.delete, url, json=json)

    async def read(self, *path: str):
        url = self._make_url(*path)
        return await self._execute_with_retry(requests.get, url)

    async def update(self, *path: str, json: dict | None = None):
        url = self._make_url(*path)
        return await self._execute_with_retry(requests.patch, url, json=json)


class SubscriptionRenewer:
    def __init__(
        self, auth: AuthClient, base_url: str, config: dict, notifier: TeamsNotifier
    ):
        self._config: dict[str, str] = config
        self._expiration = 0
        self._id = None
        self._notifier = notifier
        self._task: asyncio.Task = None
        self._token: str = config['token']
        self._http = _HTTPHelper(auth, base_url, config)

    @property
    def tenant_uuid(self):
        return self._config['tenant_uuid']

    def remaining_time(self) -> int:
        if not self._expiration:
            return 0
        now = datetime.now(timezone.utc)
        return int((self._expiration - now).total_seconds())

    def start(self):
        self._task = asyncio.create_task(self._run())

    def stop(self):
        self._task.cancel()

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
                subscription = await self._find_subscription()
            except (HTTPError, ValueError):
                raise
            else:
                action = 'found'
        elif response.status_code == 400:
            logger.error(
                'failed to create subscription (teams was unable to communicate with the stack)'
            )
        else:
            response.raise_for_status()
            subscription = response.json()
            action = 'created'

        self._id = subscription['id']
        self._expiration = iso8601.parse_date(subscription['expirationDateTime'])
        logger.debug(
            '%s subscription `%s` (expires in %d second(s))',
            action,
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
        expected_resource = f'/communications/presences/{user_id}'

        response = await self._http.read('subscriptions')
        response.raise_for_status()

        for subscription in response.json()['value']:
            if (
                subscription['resource'] == expected_resource
                and subscription['changeType'] == 'updated'
            ):
                return subscription
        raise ValueError(f'no compatible subsription found for user `{user_uuid}`')

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
        except (ValueError, HTTPError) as exc:
            logger.error(
                'unable to create a subscription for user `%s`: %s', user_uuid, exc
            )
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
            except HTTPError as exc:
                logger.error(
                    'failed to renew subscription for user `%s`: %s', user_uuid, exc
                )
                break
            except asyncio.CancelledError:
                break
        try:
            await self._delete_subscription()
        except HTTPError as exc:
            logger.debug(
                'failed to delete subscription for user `%s`: %s', user_uuid, exc
            )
        logger.debug('subscription renewer stopped for user `%s`', user_uuid)
        await self._notifier.unsubscribed(tenant_uuid, user_uuid)
