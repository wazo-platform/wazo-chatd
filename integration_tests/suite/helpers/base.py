# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os

from wazo_chatd_client import Client as ChatdClient
from wazo_chatd.database.queries import DAO
from wazo_chatd.database.helpers import init_db, get_dao_session, Session

from xivo_test_helpers.auth import MockUserToken
from xivo_test_helpers.auth import AuthClient
from xivo_test_helpers.asset_launching_test_case import (
    AssetLaunchingTestCase,
    NoSuchPort,
    NoSuchService,
)

from .amid import AmidClient
from .bus import BusClient
from .confd import ConfdClient
from .wait_strategy import EverythingOkWaitStrategy

DB_URI = 'postgresql://wazo-chatd:Secr7t@localhost:{port}'
DB_ECHO = os.getenv('DB_ECHO', '').lower() == 'true'

CHATD_TOKEN_TENANT_UUID = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee1'

TOKEN_UUID = '00000000-0000-0000-0000-000000000101'
TOKEN_TENANT_UUID = '00000000-0000-0000-0000-000000000201'
TOKEN_SUBTENANT_UUID = '00000000-0000-0000-0000-000000000202'
TOKEN_USER_UUID = '00000000-0000-0000-0000-000000000301'

UNKNOWN_UUID = '00000000-0000-0000-0000-000000000000'
WAZO_UUID = '00000000-0000-0000-0000-0000000c4a7d'

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

        cls.create_token()
        cls.reset_clients()
        cls.wait_strategy.wait(cls)

    @classmethod
    def create_token(cls):
        cls.auth = cls.make_auth()
        if not cls.auth:
            return

        token = MockUserToken(
            TOKEN_UUID,
            TOKEN_USER_UUID,
            metadata={'uuid': TOKEN_USER_UUID, 'tenant_uuid': TOKEN_TENANT_UUID},
        )
        cls.auth.set_token(token)
        cls.auth.set_tenants(
            {'uuid': CHATD_TOKEN_TENANT_UUID, 'name': 'chatd-token', 'parent_uuid': CHATD_TOKEN_TENANT_UUID},
            {'uuid': TOKEN_TENANT_UUID, 'name': 'name1', 'parent_uuid': TOKEN_TENANT_UUID},
            {'uuid': TOKEN_SUBTENANT_UUID, 'name': 'name2', 'parent_uuid': TOKEN_TENANT_UUID},
        )

    @classmethod
    def reset_clients(cls):
        cls.amid = cls.make_amid()
        cls.chatd = cls.make_chatd()
        cls.auth = cls.make_auth()
        cls.confd = cls.make_confd()
        cls.bus = cls.make_bus()

    @classmethod
    def make_chatd(cls, token=TOKEN_UUID):
        try:
            port = cls.service_port(9304, 'chatd')
        except NoSuchService as e:
            logger.debug(e)
            return
        return ChatdClient('localhost', port=port, token=token, verify_certificate=False)

    @classmethod
    def make_amid(cls):
        try:
            port = cls.service_port(9491, 'amid')
        except (NoSuchService, NoSuchPort) as e:
            logger.debug(e)
            return
        return AmidClient('localhost', port=port)

    @classmethod
    def make_auth(cls):
        try:
            port = cls.service_port(9497, 'auth')
        except NoSuchService as e:
            logger.debug(e)
            return
        return AuthClient('localhost', port=port)

    @classmethod
    def make_confd(cls):
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
        self._dao.tenant.find_or_create(TOKEN_TENANT_UUID)
        self._dao.tenant.find_or_create(TOKEN_SUBTENANT_UUID)
        self._session.commit()

    def tearDown(self):
        self._Session.rollback()
        self._Session.remove()
