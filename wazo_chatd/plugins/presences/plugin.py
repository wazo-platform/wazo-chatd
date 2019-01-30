# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_chatd.database.queries.user import UserDAO

from .http import PresenceListResource
from .services import PresenceService


class Plugin:

    def load(self, dependencies):
        api = dependencies['api']
        service = PresenceService(UserDAO())

        api.add_resource(
            PresenceListResource,
            '/users/presences',
            resource_class_args=[service],
        )
