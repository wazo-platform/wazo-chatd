# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo.auth_verifier import required_acl

from wazo_chatd.auth import required_master_tenant
from wazo_chatd.http import AuthResource


class ConfigResource(AuthResource):
    def __init__(self, config):
        self._config = config

    @required_master_tenant()
    @required_acl('chatd.config.read')
    def get(self):
        return dict(self._config), 200
