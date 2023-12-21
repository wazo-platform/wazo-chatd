# Copyright 2022-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_auth_client import Client as AuthClient
from wazo_confd_client import Client as ConfdClient

from wazo_chatd.plugins.presences.notifier import PresenceNotifier
from wazo_chatd.plugins.presences.services import PresenceService

from .bus_consume import BusEventHandler
from .http import TeamsPresenceResource
from .log import make_logger
from .notifier import TeamsNotifier
from .services import TeamsService

logger = make_logger(__name__)


class Plugin:
    def load(self, dependencies):
        aio = dependencies['aio']
        api = dependencies['api']
        bus_consumer = dependencies['bus_consumer']
        bus_publisher = dependencies['bus_publisher']
        config = dependencies['config']
        dao = dependencies['dao']

        auth = AuthClient(**config['auth'])
        confd = ConfdClient(**config['confd'])

        token_changed_subscribe = dependencies['token_changed_subscribe']
        token_changed_subscribe(auth.set_token)
        token_changed_subscribe(confd.set_token)

        presence_notifier = PresenceNotifier(bus_publisher)
        presence_service = PresenceService(dao, presence_notifier)

        notifier = TeamsNotifier(aio, bus_publisher)

        service = TeamsService(
            aio, auth, confd, config, dao, notifier, presence_service
        )
        service.initialize()

        events_handler = BusEventHandler(aio, bus_consumer, service)
        events_handler.subscribe()

        api.add_resource(
            TeamsPresenceResource,
            '/users/<user_uuid>/teams/presence',
            resource_class_args=(service,),
        )
