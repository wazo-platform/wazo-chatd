# Copyright 2022-2024 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_bus.resources.common.event import UserEvent

from wazo_chatd.asyncio_ import CoreAsyncio
from wazo_chatd.bus import BusPublisher


class TeamsPresenceSynchronizationStartedEvent(UserEvent):
    name = 'user_teams_presence_synchronization_started'
    routing_key_fmt = 'chatd.users.{user_uuid}.teams_sync.started'

    def __init__(self, tenant_uuid, user_uuid):
        content = {'user_uuid': user_uuid}
        super().__init__(content, tenant_uuid, user_uuid)


class TeamsPresenceSynchronizationStoppedEvent(UserEvent):
    name = 'user_teams_presence_synchronization_stopped'
    routing_key_fmt = 'chatd.users.{user_uuid}.teams_sync.stopped'

    def __init__(self, tenant_uuid, user_uuid):
        content = {'user_uuid': user_uuid}
        super().__init__(content, tenant_uuid, user_uuid)


class TeamsNotifier:
    def __init__(self, aio: CoreAsyncio, bus_publisher: BusPublisher):
        self._aio = aio
        self._bus = bus_publisher

    async def subscribed(self, tenant_uuid, user_uuid) -> None:
        event = TeamsPresenceSynchronizationStartedEvent(tenant_uuid, user_uuid)
        await self._aio.execute(self._bus.publish, event)

    async def unsubscribed(self, tenant_uuid, user_uuid) -> None:
        event = TeamsPresenceSynchronizationStoppedEvent(tenant_uuid, user_uuid)
        await self._aio.execute(self._bus.publish, event)
