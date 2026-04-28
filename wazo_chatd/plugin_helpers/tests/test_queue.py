# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import threading
import unittest

import pytest

from wazo_chatd.plugin_helpers.queue import AsyncQueue, QueueFull


class TestAsyncQueueBasics(unittest.TestCase):
    def test_append_increases_length(self) -> None:
        queue: AsyncQueue[str] = AsyncQueue()
        assert len(queue) == 0

        queue.append('a')
        queue.append('b')

        assert len(queue) == 2

    def test_append_raises_when_full(self) -> None:
        queue: AsyncQueue[int] = AsyncQueue(maxsize=3)
        queue.append(1)
        queue.append(2)
        queue.append(3)

        with pytest.raises(QueueFull):
            queue.append(4)

    def test_queue_full_exception_exposes_maxsize(self) -> None:
        queue: AsyncQueue[int] = AsyncQueue(maxsize=2)
        queue.append(1)
        queue.append(2)

        with pytest.raises(QueueFull) as exc_info:
            queue.append(3)

        assert exc_info.value.maxsize == 2


class TestAsyncQueueIteration(unittest.IsolatedAsyncioTestCase):
    async def test_iterate_buffered_items(self) -> None:
        queue: AsyncQueue[str] = AsyncQueue()
        queue.append('a')
        queue.append('b')
        queue.append('c')

        results = []
        async for item in queue:
            results.append(item)
            if len(results) == 3:
                break

        assert results == ['a', 'b', 'c']

    async def test_consumer_blocks_until_append(self) -> None:
        queue: AsyncQueue[str] = AsyncQueue()

        async def consume() -> str:
            async for item in queue:
                return item
            return ''

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.01)
        assert not task.done()

        queue.append('hello')
        result = await asyncio.wait_for(task, timeout=1.0)

        assert result == 'hello'

    async def test_consumer_wakes_via_event_not_polling(self) -> None:
        queue: AsyncQueue[str] = AsyncQueue()
        received: list[str] = []

        async def consume() -> None:
            async for item in queue:
                received.append(item)
                if len(received) == 2:
                    return

        task = asyncio.create_task(consume())
        await asyncio.sleep(0)
        queue.append('a')
        await asyncio.sleep(0)
        queue.append('b')

        await asyncio.wait_for(task, timeout=1.0)
        assert received == ['a', 'b']

    async def test_cancelled_consumer_releases_cleanly(self) -> None:
        queue: AsyncQueue[str] = AsyncQueue()

        async def consume() -> str:
            async for item in queue:
                return item
            return ''

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_append_after_consumer_already_waiting(self) -> None:
        queue: AsyncQueue[int] = AsyncQueue()
        results: list[int] = []

        async def consume() -> None:
            async for item in queue:
                results.append(item)
                if len(results) == 3:
                    return

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.01)

        for i in range(3):
            queue.append(i)

        await asyncio.wait_for(task, timeout=1.0)
        assert results == [0, 1, 2]


class TestAsyncQueueCrossThread(unittest.IsolatedAsyncioTestCase):
    async def test_producer_on_different_thread(self) -> None:
        queue: AsyncQueue[int] = AsyncQueue()
        received: list[int] = []

        async def consume() -> None:
            async for item in queue:
                received.append(item)
                if len(received) == 5:
                    return

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.01)

        def produce() -> None:
            for i in range(5):
                queue.append(i)

        producer = threading.Thread(target=produce)
        producer.start()
        producer.join()

        await asyncio.wait_for(task, timeout=1.0)
        assert received == [0, 1, 2, 3, 4]

    async def test_multiple_producer_threads(self) -> None:
        queue: AsyncQueue[int] = AsyncQueue()
        received: list[int] = []
        total = 50

        async def consume() -> None:
            async for item in queue:
                received.append(item)
                if len(received) == total:
                    return

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.01)

        def produce(base: int) -> None:
            for i in range(base, base + 10):
                queue.append(i)

        threads = [
            threading.Thread(target=produce, args=(base,))
            for base in (0, 10, 20, 30, 40)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        await asyncio.wait_for(task, timeout=2.0)
        assert sorted(received) == list(range(total))
