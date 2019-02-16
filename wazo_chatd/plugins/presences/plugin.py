# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from xivo_amid_client import Client as AmidClient
from xivo_auth_client import Client as AuthClient
from xivo_confd_client import Client as ConfdClient

from .bus_consume import BusEventHandler
from .http import PresenceListResource, PresenceItemResource
from .notifier import PresenceNotifier
from .services import PresenceService
from .initiator import Initiator

logger = logging.getLogger(__name__)


class Plugin:

    def load(self, dependencies):
        api = dependencies['api']
        config = dependencies['config']
        dao = dependencies['dao']
        bus_consumer = dependencies['bus_consumer']
        bus_publisher = dependencies['bus_publisher']

        notifier = PresenceNotifier(bus_publisher)
        service = PresenceService(dao, notifier)
        initialization = config['initialization']

        auth = AuthClient(**config['auth'])
        initiator = Initiator(dao, auth)
        if initialization['tenants']:
            initiator.initiate_tenants()
        if initialization['users']:
            confd = ConfdClient(**config['confd'])
            initiator.initiate_users(confd)
        if initialization['lines']:
            amid = AmidClient(**config['amid'])
            initiator.initiate_lines_state(amid)
        if initialization['sessions']:
            initiator.initiate_sessions()
        if initialization['connections']:
            logger.debug('Initialize connections is not implemented')

        bus_event_handler = BusEventHandler(dao, notifier)
        bus_event_handler.subscribe(bus_consumer)

        api.add_resource(
            PresenceListResource,
            '/users/presences',
            resource_class_args=[service],
        )

        api.add_resource(
            PresenceItemResource,
            '/users/<uuid:user_uuid>/presences',
            resource_class_args=[service],
        )
