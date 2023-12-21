# Copyright 2019-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from uuid import uuid4

import requests


class ConfdClient:
    def __init__(self, host, port):
        self._host = host
        self._port = port

    def url(self, *parts):
        return f'http://{self._host}:{self._port}/{"/".join(parts)}'

    def set_users(self, *mock_users):
        url = self.url('_set_response')
        body = {
            'response': 'users',
            'content': {user['uuid']: user for user in mock_users},
        }
        requests.post(url, json=body)

    def set_ingresses(self, *mock_uris):
        url = self.url('_set_response')
        resource_uuid = str(uuid4())
        body = {
            'response': 'ingresses',
            'content': {
                resource_uuid: {'uri': uri, 'uuid': resource_uuid} for uri in mock_uris
            },
        }
        requests.post(url, json=body)
