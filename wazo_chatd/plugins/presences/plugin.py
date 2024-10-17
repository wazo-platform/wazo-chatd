# Copyright 2019-2024 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from wazo_amid_client import Client as AmidClient
from wazo_auth_client import Client as AuthClient
from wazo_confd_client import Client as ConfdClient

from .bus_consume import BusEventHandler
from .http import PresenceItemResource, PresenceListResource
from .initiator import Initiator
from .initiator_thread import InitiatorThread
from .notifier import PresenceNotifier
from .services import PresenceService
from .validator import status_validator

logger = logging.getLogger(__name__)


class Plugin:
    def load(self, dependencies):
        api = dependencies['api']
        config = dependencies['config']
        dao = dependencies['dao']
        bus_consumer = dependencies['bus_consumer']
        bus_publisher = dependencies['bus_publisher']
        status_aggregator = dependencies['status_aggregator']
        status_validator.set_config(status_aggregator, config)

        notifier = PresenceNotifier(bus_publisher)
        service = PresenceService(dao, notifier)
        initialization = config['initialization']

        auth = AuthClient(**config['auth'])
        amid = AmidClient(**config['amid'])
        confd = ConfdClient(**config['confd'])
        initiator = Initiator(dao, auth, amid, confd)
        status_aggregator.add_provider(initiator.provide_status)

        initiator_thread = InitiatorThread(initiator)

        if initialization['enabled']:
            thread_manager = dependencies['thread_manager']
            thread_manager.manage(initiator_thread)

        bus_event_handler = BusEventHandler(dao, notifier, initiator_thread)
        bus_event_handler.subscribe(bus_consumer)

        api.add_resource(
            PresenceListResource, '/users/presences', resource_class_args=[service]
        )

        api.add_resource(
            PresenceItemResource,
            '/users/<uuid:user_uuid>/presences',
            resource_class_args=[service],
        )
