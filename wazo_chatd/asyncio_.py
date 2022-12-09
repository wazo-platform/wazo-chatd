# Copyright 2022-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0+

import asyncio
import logging

from functools import partial
from threading import Thread
from typing import Coroutine


logger = logging.getLogger("asyncio")


class CoreAsyncio:
    def __init__(self):
        name: str = 'Asyncio-Thread'
        self._loop = loop = asyncio.new_event_loop()
        self._thread: Thread = Thread(target=loop.run_forever, name=name, daemon=True)

    @property
    def loop(self):
        return self._loop

    def __enter__(self):
        self.start()

    def __exit__(self, *args):
        self.stop()

    def start(self):
        if self._thread.is_alive():
            raise RuntimeError('CoreAsyncio thread is already started')
        self._thread.start()
        logger.debug('CoreAsyncio thread started')

    def stop(self):
        if not self._thread.is_alive():
            raise RuntimeError('CoreAsyncio thread is not currently running')
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        logger.debug('CoreAsyncio thread terminated')

    def schedule_coroutine(self, coro: Coroutine):
        return asyncio.run_coroutine_threadsafe(coro, loop=self.loop)

    async def execute(self, func, *args, **kwargs):
        fn = partial(func, *args, **kwargs)
        return await self.loop.run_in_executor(None, fn)
