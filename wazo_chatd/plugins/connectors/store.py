# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
import time
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from requests.exceptions import HTTPError

from wazo_chatd.plugins.connectors.connector import Connector
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry

if TYPE_CHECKING:
    from wazo_auth_client import Client as AuthClient

CacheKey = tuple[str, str]

DEFAULT_CACHE_TTL: float = 300.0
POPULATE_CONCURRENCY: int = 20

logger = logging.getLogger(__name__)


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
        # One-shot signal — set when priority (runner-driven) population
        # completes. Webhook-mode backends may still be populating in the
        # background when this fires.
        self._populated: concurrent.futures.Future[None] = concurrent.futures.Future()
        # Ensures populate runs at most once concurrently. Non-blocking
        # acquire — second caller returns immediately.
        self._populate_lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._cache)

    def __iter__(self) -> Iterator[Connector]:
        return iter(self._cache.values())

    def items(self) -> Iterator[tuple[CacheKey, Connector]]:
        # Snapshot — protects iteration against concurrent writes from
        # populate's worker pool.
        return iter(list(self._cache.items()))

    @property
    def is_populated(self) -> bool:
        return self._populated.done()

    def find_by_backend(self, backend: str, tenant_uuid: str) -> Connector | None:
        return self._cache.get((tenant_uuid, backend))

    def populate(self, tenant_backends: Iterable[tuple[str, str]]) -> None:
        """Pre-load the cache.

        Non-webhook backends are populated first; ``_populated`` fires
        as soon as they are ready so pollers/listeners can spawn.
        Webhook-mode backends are populated afterwards in the same
        thread — webhook dispatch tolerates brief startup lag (cache
        miss → ``find_by_backend`` returns None, provider retries).

        Idempotent and non-blocking — concurrent callers return
        immediately instead of racing.
        """
        if not self._populate_lock.acquire(blocking=False):
            return

        try:
            if self._populated.done():
                return

            registered = set(self._registry.available_backends())
            if unknown := set(self._connectors_config) - registered:
                logger.warning(
                    'Configuration found for unknown connector backend(s): %s',
                    sorted(unknown),
                )

            priority_backends = {
                backend
                for backend, cfg in self._connectors_config.items()
                if (cfg or {}).get('mode', 'webhook') != 'webhook'
            }

            pairs = set(tenant_backends)
            priority = {pair for pair in pairs if pair[1] in priority_backends}
            deferred = pairs - priority

            self._fetch_batch(priority)
            self._populated.set_result(None)
            logger.info(
                'Populated connector store (priority=%d, deferred=%d)',
                len(priority),
                len(deferred),
            )
            self._fetch_batch(deferred)
        finally:
            self._populate_lock.release()

    async def wait_populated(self) -> None:
        """Resolve when runner-driven populate has completed."""
        await asyncio.wrap_future(self._populated)

    def _fetch_batch(self, pairs: set[tuple[str, str]]) -> None:
        # At scale, consider direct async httpx (bypasses the
        # wazo_auth_client sync pool) — trades off wire-format coupling.
        if not pairs:
            return

        with ThreadPoolExecutor(
            max_workers=POPULATE_CONCURRENCY,
            thread_name_prefix='connector-store-populate',
        ) as pool:
            list(
                pool.map(
                    lambda pair: self._fetch_and_cache(pair[1], pair[0]),
                    pairs,
                )
            )

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
            auth_config = dict(
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

        try:
            backend_cls = self._registry.get_backend(backend)
        except KeyError:
            logger.warning(
                'Unknown backend %r referenced for tenant %s', backend, tenant_uuid
            )
            return None

        backend_config = self._connectors_config.get(backend, {})
        try:
            instance = backend_cls(tenant_uuid, auth_config, backend_config)
        except Exception:
            logger.exception(
                'Failed to instantiate backend %r for tenant %s', backend, tenant_uuid
            )
            return None

        self._cache[key] = instance
        self._timestamps[key] = time.monotonic()
        logger.info('Loaded connector instance %r for tenant %s', backend, tenant_uuid)
        return instance
