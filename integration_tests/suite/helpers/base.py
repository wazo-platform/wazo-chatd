# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from wazo_chatd_client import Client as ChatdClient
from xivo_test_helpers.asset_launching_test_case import AssetLaunchingTestCase

VALID_TOKEN = 'valid-token'


class BaseIntegrationTest(AssetLaunchingTestCase):

    assets_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'assets'))
    service = 'chatd'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chatd = cls.make_chatd(VALID_TOKEN)

    @classmethod
    def make_chatd(cls, token):
        return ChatdClient(
            'localhost',
            cls.service_port(9304, 'chatd'),
            token=token,
            verify_certificate=False,
        )
