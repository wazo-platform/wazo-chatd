# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os

from wazo_chatd_client import Client as ChatdClient
from wazo_chatd.database.queries import DAO
from wazo_chatd.database.helpers import init_db, get_dao_session, Session

from xivo_test_helpers.auth import AuthClient
from xivo_test_helpers.asset_launching_test_case import AssetLaunchingTestCase, NoSuchService

from .amid import AmidClient
from .bus import BusClient
from .confd import ConfdClient
from .wait_strategy import EverythingOkWaitStrategy

VALID_TOKEN = 'valid-token-multi-tenant'

DB_URI = 'postgresql://wazo-chatd:Secr7t@localhost:{port}'
DB_ECHO = os.getenv('DB_ECHO', '').lower() == 'true'

VALID_TOKEN = 'valid-token-multitenant'
MASTER_TENANT_UUID = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee1'
SUBTENANT_UUID = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee2'
UNKNOWN_UUID = '00000000-0000-0000-0000-000000000000'
DIFFERENT_TENANT_UUID = 'ffffffff-ffff-ffff-ffff-ffffffffffff'

logger = logging.getLogger(__name__)


class BaseIntegrationTest(AssetLaunchingTestCase):

    assets_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'assets'))
    service = 'chatd'
    wait_strategy = EverythingOkWaitStrategy()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        init_db(DB_URI.format(port=cls.service_port(5432, 'postgres')), echo=DB_ECHO)
        cls._Session = Session

        cls.amid = cls.make_amid(VALID_TOKEN)
        cls.chatd = cls.make_chatd(VALID_TOKEN)
        cls.auth = cls.make_auth(VALID_TOKEN)
        cls.confd = cls.make_confd(VALID_TOKEN)
        cls.bus = cls.make_bus()
        cls.wait_strategy.wait(cls)

    @classmethod
    def make_chatd(cls, token):
        try:
            port = cls.service_port(9304, 'chatd')
        except NoSuchService as e:
            logger.debug(e)
            return
        return ChatdClient('localhost', port=port, token=token, verify_certificate=False)

    @classmethod
    def make_amid(cls, token):
        try:
            port = cls.service_port(9491, 'amid')
        except NoSuchService as e:
            logger.debug(e)
            return
        return AmidClient('localhost', port=port)

    @classmethod
    def make_auth(cls, token):
        try:
            port = cls.service_port(9497, 'auth')
        except NoSuchService as e:
            logger.debug(e)
            return
        return AuthClient('localhost', port=port)

    @classmethod
    def make_confd(cls, token):
        try:
            port = cls.service_port(9486, 'confd')
        except NoSuchService as e:
            logger.debug(e)
            return
        return ConfdClient('localhost', port=port)

    @classmethod
    def make_bus(cls):
        try:
            port = cls.service_port(5672, 'rabbitmq')
        except NoSuchService as e:
            logger.debug(e)
            return
        return BusClient.from_connection_fields(host='localhost', port=port)

    @property
    def _session(self):
        return get_dao_session()

    def setUp(self):
        super().setUp()
        self._dao = DAO()
        self._dao.tenant.find_or_create(MASTER_TENANT_UUID)
        self._dao.tenant.find_or_create(SUBTENANT_UUID)

    def tearDown(self):
        self._Session.rollback()
        self._Session.remove()
