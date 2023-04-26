# Copyright 2022-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import requests


class MicrosoftGraphClient:
    def __init__(self, host, port):
        self._host = host
        self._port = port

    def url(self, *parts):
        return f'http://{self._host}:{self._port}/{"/".join(parts)}'

    def register_user(self, user_uuid):
        url = self.url('_register')
        response = requests.post(url, params={'user': str(user_uuid)})
        response.raise_for_status()
        return response.json()

    def unregister_user(self, user_uuid):
        url = self.url('_unregister')
        return requests.post(url, params={'user': str(user_uuid)})

    def set_presence(self, user_uuid, availability):
        url = self.url('_set_presence')
        data = {
            'availability': availability,
        }
        return requests.post(url, params={'user': str(user_uuid)}, json=data)
