# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import random
import threading
import time
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from requests.exceptions import HTTPError, RequestException

from wazo_chatd.plugins.connectors.connector import Connector
from wazo_chatd.plugins.connectors.exceptions import (
    AuthServiceUnavailableException,
    BackendNotConfiguredException,
    UnknownBackendException,
)
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry

if TYPE_CHECKING:
    from wazo_auth_client import Client as AuthClient

CacheKey = tuple[str, str]

DEFAULT_CACHE_TTL: float = 300.0
POPULATE_CONCURRENCY: int = 20
POPULATE_FETCH_TIMEOUT: float = 30.0
TTL_JITTER: float = 0.2

logger = logging.getLogger(__name__)


class ConnectorStore:
    """Lazy, TTL-based cache of configured connector instances.

    Keyed by ``(tenant_uuid, backend)``.  Both sync and async sides
    read from cache via :meth:`peek`.  The async side
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
        self._expires_at: dict[CacheKey, float] = {}
        self._cache_epoch: dict[CacheKey, int] = {}
        # One-shot signal — set when priority (runner-driven) population
        # completes. Webhook-mode backends may still be populating in the
        # background when this fires.
        self._populated: concurrent.futures.Future[None] = concurrent.futures.Future()
        # Ensures populate runs at most once concurrently. Non-blocking
        # acquire — second caller returns immediately.
        self._populate_lock = threading.Lock()
        # Single-flight: concurrent fetches for the same key share one
        # wazo-auth round-trip. Lock guards membership only; waiting
        # happens off-lock.
        self._pending_fetches: dict[CacheKey, concurrent.futures.Future[Connector]] = {}
        self._fetch_lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._cache)

    def __iter__(self) -> Iterator[Connector]:
        # Snapshot — protects iteration against concurrent writes from
        # populate's worker pool.
        return iter(list(self._cache.values()))

    def items(self) -> Iterator[tuple[CacheKey, Connector]]:
        return iter(list(self._cache.items()))

    @property
    def is_populated(self) -> bool:
        if not self._populated.done():
            return False
        return self._populated.exception() is None

    def peek(self, backend: str, tenant_uuid: str) -> Connector | None:
        return self._cache.get((tenant_uuid, backend))

    def populate(self, tenant_backends: Iterable[tuple[str, str]]) -> None:
        """Pre-load the cache.

        Non-webhook backends are populated first; ``_populated`` fires
        as soon as they are ready so pollers/listeners can spawn.
        Webhook-mode backends are populated afterwards in the same
        thread — webhook dispatch tolerates brief startup lag (cache
        miss → ``peek`` returns None, provider retries).

        Idempotent and non-blocking — concurrent callers return
        immediately instead of racing.
        """
        if not self._populate_lock.acquire(blocking=False):
            return

        try:
            if self._populated.done():
                return

            try:
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
            except Exception as e:
                self._populated.set_exception(e)
                raise

            self._populated.set_result(None)
            logger.info(
                'Populated connector store (priority=%d, deferred=%d)',
                len(priority),
                len(deferred),
            )

            try:
                self._fetch_batch(deferred)
            except Exception:
                logger.exception('Deferred connector fetch failed, continuing')
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

        pool = ThreadPoolExecutor(
            max_workers=POPULATE_CONCURRENCY,
            thread_name_prefix='connector-store-populate',
        )
        try:
            futures = {
                pool.submit(self.find, backend, tenant_uuid): (tenant_uuid, backend)
                for tenant_uuid, backend in pairs
            }
            _, not_done = concurrent.futures.wait(
                futures, timeout=POPULATE_FETCH_TIMEOUT
            )
            for future in not_done:
                tenant_uuid, backend = futures[future]
                logger.warning(
                    'Populate timed out after %.0fs for backend %r tenant %s',
                    POPULATE_FETCH_TIMEOUT,
                    backend,
                    tenant_uuid,
                )
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def drop(self, backend: str, tenant_uuid: str) -> None:
        key = (tenant_uuid, backend)
        with self._fetch_lock:
            self._cache.pop(key, None)
            self._expires_at.pop(key, None)
            self._cache_epoch[key] = self._cache_epoch.get(key, 0) + 1

    def get(self, backend: str, tenant_uuid: str) -> Connector:
        """Get cached instance if fresh, else fetch from wazo-auth; raises on failure.

        Raises:
          - :class:`UnknownBackendException` (400) — backend not registered.
          - :class:`BackendNotConfiguredException` (400) — no tenant config.
          - :class:`AuthServiceUnavailableException` (503) — transient.
        """
        if (cached := self._get_cached(backend, tenant_uuid)) is not None:
            return cached
        return self._fetch(backend, tenant_uuid)

    def find(self, backend: str, tenant_uuid: str) -> Connector | None:
        """Silent variant of :meth:`get` — logs and returns None on failure."""
        try:
            return self.get(backend, tenant_uuid)
        except UnknownBackendException:
            logger.warning(
                'Unknown backend %r referenced for tenant %s', backend, tenant_uuid
            )
        except BackendNotConfiguredException:
            logger.debug(
                'No auth config for backend %r tenant %s', backend, tenant_uuid
            )
        except AuthServiceUnavailableException:
            logger.error(
                'Failed to fetch auth config for backend %r tenant %s',
                backend,
                tenant_uuid,
            )
        except Exception:
            logger.exception(
                'Failed to instantiate backend %r for tenant %s', backend, tenant_uuid
            )
        return None

    async def refresh(self, backend: str, tenant_uuid: str) -> Connector | None:
        """Async variant of :meth:`find` that runs off the event loop."""
        return await asyncio.to_thread(self.find, backend, tenant_uuid)

    def _get_cached(self, backend: str, tenant_uuid: str) -> Connector | None:
        key = (tenant_uuid, backend)
        if time.monotonic() > self._expires_at.get(key, 0.0):
            return None
        return self._cache.get(key)

    def _fetch(self, backend: str, tenant_uuid: str) -> Connector:
        """Talk to wazo-auth, instantiate, cache, and return; raises on failure.

        Single-flight: concurrent callers for the same key share one
        wazo-auth round-trip via :attr:`_pending_fetches`.
        """
        key = (tenant_uuid, backend)
        is_leader = False

        with self._fetch_lock:
            if (cached := self._get_cached(backend, tenant_uuid)) is not None:
                return cached

            if (future := self._pending_fetches.get(key)) is None:
                future = concurrent.futures.Future()
                self._pending_fetches[key] = future
                is_leader = True

        if not is_leader:
            return future.result()

        try:
            instance = self._do_fetch(backend, tenant_uuid)
            future.set_result(instance)
            return instance
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            with self._fetch_lock:
                self._pending_fetches.pop(key, None)

    def _do_fetch(self, backend: str, tenant_uuid: str) -> Connector:
        key = (tenant_uuid, backend)

        if backend not in self._registry.available_backends():
            raise UnknownBackendException(backend)

        with self._fetch_lock:
            epoch_before = self._cache_epoch.get(key, 0)

        try:
            provider_config = dict(
                self._auth_client.external.get_config(backend, tenant_uuid=tenant_uuid)
            )
        except HTTPError as e:
            with self._fetch_lock:
                self._cache.pop(key, None)
                self._expires_at.pop(key, None)
            if getattr(e.response, 'status_code', None) == 404:
                raise BackendNotConfiguredException(backend, tenant_uuid)
            raise AuthServiceUnavailableException()
        except RequestException:
            raise AuthServiceUnavailableException()

        backend_cls = self._registry.get_backend(backend)
        connector_config = self._connectors_config.get(backend, {})
        instance = backend_cls(tenant_uuid, provider_config, connector_config)

        with self._fetch_lock:
            if self._cache_epoch.get(key, 0) != epoch_before:
                logger.info(
                    'Drop during fetch for backend %r tenant %s; '
                    'returning instance without caching',
                    backend,
                    tenant_uuid,
                )
                return instance
            jitter = random.uniform(1.0 - TTL_JITTER, 1.0 + TTL_JITTER)
            self._cache[key] = instance
            self._expires_at[key] = time.monotonic() + self._cache_ttl * jitter

        logger.info('Loaded connector instance %r for tenant %s', backend, tenant_uuid)
        return instance
