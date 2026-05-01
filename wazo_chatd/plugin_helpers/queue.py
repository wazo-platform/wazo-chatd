# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import collections
import concurrent.futures
from typing import Generic, TypeVar

T = TypeVar('T')


class QueueFull(Exception):
    """Raised when :meth:`AsyncQueue.append` is called on a full queue."""

    def __init__(self, maxsize: int) -> None:
        super().__init__(f'AsyncQueue at capacity ({maxsize})')
        self.maxsize = maxsize


class AsyncQueue(Generic[T]):
    """Thread-safe FIFO consumable as an async iterator.

    Unlike :class:`asyncio.Queue`, the producer side is loop-agnostic
    and safe from any thread — :meth:`append` needs no event loop
    reference. The consumer iterates via ``async for`` with
    event-driven wake-ups and binds to its running loop implicitly.

    Cross-thread wake-up uses :class:`concurrent.futures.Future`
    (thread-safe), bridged to the consumer's running loop via
    :func:`asyncio.wrap_future`. The producer never touches the
    consumer's loop.

    Designed for multi-producer, single-consumer usage.
    """

    def __init__(self, maxsize: int = 1000) -> None:
        self._items: collections.deque[T] = collections.deque()
        self._maxsize = maxsize
        self._wake: concurrent.futures.Future[None] | None = None

    def __len__(self) -> int:
        return len(self._items)

    def append(self, item: T) -> None:
        """Enqueue *item*. Thread-safe, loop-agnostic.

        Raises :class:`QueueFull` if the queue is at capacity.
        """
        if len(self._items) >= self._maxsize:
            raise QueueFull(self._maxsize)

        self._items.append(item)

        if (wake := self._wake) is not None and not wake.done():
            try:
                wake.set_result(None)
            except concurrent.futures.InvalidStateError:
                pass

    def reset(self) -> None:
        """Drop the consumer wake so a restarted consumer rebinds to its loop."""
        self._wake = None

    def __aiter__(self) -> AsyncQueue[T]:
        return self

    async def __anext__(self) -> T:
        while not self._items:
            wake: concurrent.futures.Future[None] = concurrent.futures.Future()
            self._wake = wake
            if self._items:
                break

            await asyncio.wrap_future(wake)

        return self._items.popleft()
