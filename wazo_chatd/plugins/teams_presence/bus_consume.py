# Copyright 2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Coroutine

from wazo_chatd.asyncio_ import CoreAsyncio
from wazo_chatd.bus import BusConsumer

from .log import make_logger
from .services import TeamsService


logger = make_logger(__name__)


class BusEventHandler:
    def __init__(
        self,
        aio: CoreAsyncio,
        bus: BusConsumer,
        teams_service: TeamsService,
    ):
        self.aio = aio
        self.bus = bus
        self.service = teams_service

    def _register_async_handler(self, event_name: str, handler: Coroutine):
        def dispatch(payload):
            self.aio.schedule_coroutine(handler(payload))

        setattr(dispatch, '__name__', handler.__name__)
        self.bus.subscribe(event_name, dispatch)

    async def on_external_auth_added(self, payload):
        user_uuid, auth_name = payload.values()

        if auth_name != 'microsoft':
            return

        try:
            await self.service.create_subscription(user_uuid)
        except Exception:
            logger.exception('an exception occured!')

    async def on_external_auth_deleted(self, payload):
        user_uuid, auth_name = payload.values()

        if auth_name != 'microsoft':
            return

        try:
            await self.service.delete_subscription(user_uuid)
        except Exception:
            logger.exception('an exception occured!')

    def subscribe(self):
        events = (
            ('auth_user_external_auth_added', self.on_external_auth_added),
            ('auth_user_external_auth_deleted', self.on_external_auth_deleted),
        )

        for event, handler in events:
            self._register_async_handler(event, handler)
