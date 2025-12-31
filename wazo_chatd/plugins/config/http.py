# Copyright 2019-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

import jsonpatch
from flask import request
from xivo.auth_verifier import required_acl

from wazo_chatd.auth import required_master_tenant
from wazo_chatd.http import AuthResource

from .schemas import config_patch_schema


class ConfigResource(AuthResource):
    def __init__(self, config):
        self._config = config

    def _toggle_debug_flag(self):
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG) if self._config['debug'] else logger.setLevel(
            self._config['log_level']
        )

    @required_master_tenant()
    @required_acl('chatd.config.read')
    def get(self):
        return dict(self._config), 200

    @required_master_tenant()
    @required_acl('chatd.config.update')
    def patch(self):
        config_patch = config_patch_schema.load(request.get_json(force=True), many=True)
        self._config = jsonpatch.apply_patch(self._config, config_patch)
        self._toggle_debug_flag()
        return dict(self._config), 200
