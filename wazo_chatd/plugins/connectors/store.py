# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from requests.exceptions import HTTPError

from wazo_chatd.plugins.connectors.connector import Connector
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry

if TYPE_CHECKING:
    from wazo_auth_client import Client as AuthClient

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL: float = 300.0

CacheKey = tuple[str, str]


class ConnectorStore:
    """Lazy, TTL-based cache of configured connector instances.

    Keyed by ``(tenant_uuid, backend)``.  Both sync and async sides
    read from cache via :meth:`find_by_backend`.  The async side
    drives fetches via :meth:`refresh`.
    """

    def __init__(
        self,
        auth_client: AuthClient,
        registry: ConnectorRegistry,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        connectors_config: dict[str, Any] | None = None,
    ) -> None:
        self._auth_client = auth_client
        self._registry = registry
        self._cache_ttl = cache_ttl
        self._connectors_config = connectors_config or {}
        self._cache: dict[CacheKey, Connector] = {}
        self._timestamps: dict[CacheKey, float] = {}

    def __len__(self) -> int:
        return len(self._cache)

    def __iter__(self) -> Iterator[Connector]:
        return iter(self._cache.values())

    def find_by_backend(self, backend: str, tenant_uuid: str) -> Connector | None:
        return self._cache.get((tenant_uuid, backend))

    async def refresh(self, backend: str, tenant_uuid: str) -> Connector | None:
        key = (tenant_uuid, backend)
        ts = self._timestamps.get(key, 0.0)
        if not self._is_expired(ts):
            return self._cache.get(key)

        if backend not in self._registry.available_backends():
            return None

        return await asyncio.to_thread(self._fetch_and_cache, backend, tenant_uuid)

    def _is_expired(self, timestamp: float) -> bool:
        return (time.monotonic() - timestamp) > self._cache_ttl

    def _fetch_and_cache(self, backend: str, tenant_uuid: str) -> Connector | None:
        key = (tenant_uuid, backend)
        try:
            config = dict(
                self._auth_client.external.get_config(backend, tenant_uuid=tenant_uuid)
            )
        except HTTPError as e:
            status = getattr(e.response, 'status_code', None)
            if status == 404:
                logger.debug(
                    'No auth config for backend %r tenant %s', backend, tenant_uuid
                )
            else:
                logger.error(
                    'Failed to fetch auth config for backend %r tenant %s: %s',
                    backend,
                    tenant_uuid,
                    e,
                )
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)
            return None

        cls = self._registry.get_backend(backend)
        instance = cls(tenant_uuid, config, self._connectors_config.get(backend, {}))
        self._cache[key] = instance
        self._timestamps[key] = time.monotonic()
        logger.info('Loaded connector instance %r for tenant %s', backend, tenant_uuid)
        return instance
