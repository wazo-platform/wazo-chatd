# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from xivo_auth_client import Client as AuthClient

from wazo_chatd.database.queries.user import UserDAO

from .http import PresenceListResource, PresenceItemResource
from .services import PresenceService
from .initiator import Initiator

logger = logging.getLogger(__name__)


class Plugin:

    def load(self, dependencies):
        api = dependencies['api']
        config = dependencies['config']
        service = PresenceService(UserDAO())
        initialization = config['initialization']

        auth = AuthClient(**config['auth'])
        initiator = Initiator(auth)
        if initialization['tenants']:
            logger.debug('Initialize tenants is not implemented')
        if initialization['users']:
            logger.debug('Initialize users is not implemented')
        if initialization['lines']:
            logger.debug('Initialize lines is not implemented')
        if initialization['sessions']:
            logger.debug('Initialize sessions is not implemented')
        if initialization['connections']:
            logger.debug('Initialize connections is not implemented')

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
