# Copyright 2022-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from wazo_chatd_client import Client as ChatdClient
from wazo_confd_client import Client as ConfdClient

from .resource import TeamsResource
from .services import TeamsServices


logger = logging.getLogger(__name__)


class Plugin:
    def load(self, dependencies):
        api = dependencies['api']
        config = dependencies['config']

        chatd = ChatdClient('localhost', verify_certificate=False)
        confd = ConfdClient(**config['confd'])

        token_changed_subscribe = dependencies['token_changed_subscribe']
        token_changed_subscribe(chatd.set_token)
        token_changed_subscribe(confd.set_token)
        services = TeamsServices(chatd, confd)

        api.add_resource(
            TeamsResource,
            '/users/<user_uuid>/teams/presence',
            resource_class_args=(services,),
        )
        logger.info('[Microsoft Teams Presence] succesfully loaded plugin')
