# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Per-key asyncio.Lock for serializing coroutines that share a logical resource.

Locks are created on demand and dropped when no waiters remain so the map does
not grow unbounded for short-lived keys.
"""

from __future__ import annotations

import asyncio
from collections.abc import Hashable


class KeyedLock:
    def __init__(self) -> None:
        self._locks: dict[Hashable, asyncio.Lock] = {}

    def acquire(self, key: Hashable) -> _LockGuard:
        return _LockGuard(self, key)

    def _get(self, key: Hashable) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def _maybe_drop(self, key: Hashable) -> None:
        lock = self._locks.get(key)
        if lock is not None and not lock.locked() and not lock._waiters:
            del self._locks[key]


class _LockGuard:
    def __init__(self, owner: KeyedLock, key: Hashable) -> None:
        self._owner = owner
        self._key = key
        self._lock: asyncio.Lock | None = None

    async def __aenter__(self) -> None:
        self._lock = self._owner._get(self._key)
        await self._lock.acquire()

    async def __aexit__(self, *_exc: object) -> None:
        if self._lock is not None:
            self._lock.release()
        self._owner._maybe_drop(self._key)
