# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Async helpers for integration tests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from wazo_chatd.database.async_helpers import async_session_scope, init_async_db

from .base import DB_URI


def run_async(
    func: Callable[..., Awaitable[Any]],
) -> Callable[..., Any]:
    """Run an async test method inside an async DB session.

    Spawns a fresh async engine + session scope per test. The test
    method sees data committed by the surrounding sync session
    (e.g. via the ``@fixtures.db.room`` decorator); writes performed
    inside the async session are independent.

    Stacks under fixture decorators::

        @fixtures.db.room()
        @run_async
        async def test_foo(self, room):
            await AsyncRoomDAO().add_message(room, msg)
    """

    @wraps(func)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        port = self.asset_cls.service_port(5432, 'postgres')
        db_uri = DB_URI.format(port=port)

        async def _run() -> Any:
            engine, factory = init_async_db(db_uri)
            try:
                async with async_session_scope(factory):
                    return await func(self, *args, **kwargs)
            finally:
                await engine.dispose()

        return asyncio.run(_run())

    return wrapper
