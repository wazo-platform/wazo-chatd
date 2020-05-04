# Copyright 2019-2020 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import requests


class ConfdClient:
    def __init__(self, host, port):
        self._host = host
        self._port = port

    def url(self, *parts):
        return 'http://{host}:{port}/{path}'.format(
            host=self._host, port=self._port, path='/'.join(parts)
        )

    def set_users(self, *mock_users):
        url = self.url('_set_response')
        body = {
            'response': 'users',
            'content': {user['uuid']: user for user in mock_users},
        }
        requests.post(url, json=body)
