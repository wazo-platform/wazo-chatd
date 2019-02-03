# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later


class Initiator:

    def __init__(self, auth):
        self._auth = auth
        self._token = None

    @property
    def token(self):
        if not self._token:
            self._token = self._auth.token.new(expiration=120)['token']
        return self._token
