# Copyright 2022-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from wazo_chatd_client import Client as ChatdClient
from wazo_confd_client import Client as ConfdClient

logger = logging.getLogger(__name__)

PRESENCES_MAP = {
    'Available': 'available',
    'AvailableIdle': 'available',
    'Away': 'away',
    'BeRightBack': 'away',
    'Busy': 'unavailable',
    'BusyIdle': 'unavailable',
    'DoNotDisturb': 'unavailable',
    'Offline': 'invisible',
    'PresenceUnknown': 'invisible',
}


class TeamsServices:
    def __init__(self, chatd_client: ChatdClient, confd_client: ConfdClient):
        self.chatd = chatd_client
        self.confd = confd_client

    def update_presence(self, payload, user_uuid):
        presence = payload['value'][0]['resourceData']
        print(payload)
        if not presence:
            logger.error('received empty payload')
            return

        state = PRESENCES_MAP.get(presence['availability'])

        # dnd = presence['activity'] in (
        #     'DoNotDisturb',
        #     'InACall',
        #     'InAConferenceCall',
        #     'InAMeeting',
        #     'Presenting',
        # )

        # self.confd.users(user_uuid).update_service(
        #     'dnd', ({'enabled': True} if dnd else {'enabled': False})
        # )

        logger.debug(f'updating `{user_uuid}` presence to {state}')

        data = {'uuid': user_uuid, 'state': state, 'status': presence['activity']}
        return self.chatd.user_presences.update(data)
