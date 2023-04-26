# Copyright 2019-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import requests


class AmidClient:
    def __init__(self, host, port):
        self._host = host
        self._port = port

    def url(self, *parts):
        return f'http://{self._host}:{self._port}/{"/".join(parts)}'

    def set_devicestatelist(self, *events):
        url = self.url('_set_response_action')
        body = {'response': 'DeviceStateList', 'content': events}
        requests.post(url, json=body)

    def set_coreshowchannels(self, *events):
        url = self.url('_set_response_action')
        body = {'response': 'CoreShowChannels', 'content': events}
        requests.post(url, json=body)
