# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypedDict

from flask_restful import Api
from xivo.status import StatusAggregator

from wazo_chatd.asyncio_ import CoreAsyncio
from wazo_chatd.bus import BusConsumer, BusPublisher
from wazo_chatd.database.queries import DAO
from wazo_chatd.plugin_helpers.hooks import Hooks
from wazo_chatd.thread_manager import ThreadManager


class PluginDependencies(TypedDict):
    api: Api
    aio: CoreAsyncio
    config: dict[str, Any]
    dao: DAO
    bus_consumer: BusConsumer
    bus_publisher: BusPublisher
    status_aggregator: StatusAggregator
    thread_manager: ThreadManager
    token_changed_subscribe: Callable[[Callable[..., None]], None]
    next_token_changed_subscribe: Callable[[Callable[..., None]], None]
    hooks: Hooks
