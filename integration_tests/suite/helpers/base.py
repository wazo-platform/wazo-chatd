# Copyright 2019-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest
import logging
import os
import unittest
import uuid

from wazo_chatd_client import Client as ChatdClient
from wazo_chatd.database.queries import DAO
from wazo_chatd.database.helpers import init_db, Session

from wazo_test_helpers.auth import (
    AuthClient,
    MockCredentials,
    MockUserToken,
)
from wazo_test_helpers import until
from wazo_test_helpers.asset_launching_test_case import (
    AssetLaunchingTestCase,
    NoSuchPort,
    NoSuchService,
)

from .amid import AmidClient
from .bus import BusClient
from .confd import ConfdClient
from .wait_strategy import (
    EverythingOkWaitStrategy,
    NoWaitStrategy,
    PresenceInitOkWaitStrategy,
)

DB_URI = 'postgresql://wazo-chatd:Secr7t@127.0.0.1:{port}'
DB_ECHO = os.getenv('DB_ECHO', '').lower() == 'true'

START_TIMEOUT = int(os.environ.get('INTEGRATION_TEST_TIMEOUT', '30'))

TOKEN_UUID = uuid.UUID('00000000-0000-0000-0000-000000000101')
TOKEN_TENANT_UUID = uuid.UUID('00000000-0000-0000-0000-000000000201')
TOKEN_SUBTENANT_UUID = uuid.UUID('00000000-0000-0000-0000-000000000202')
TOKEN_USER_UUID = uuid.UUID('00000000-0000-0000-0000-000000000301')

CHATD_TOKEN_TENANT_UUID = TOKEN_TENANT_UUID

UNKNOWN_UUID = uuid.UUID('00000000-0000-0000-0000-000000000000')
WAZO_UUID = uuid.UUID('00000000-0000-0000-0000-0000000c4a7d')

logger = logging.getLogger(__name__)

use_asset = pytest.mark.usefixtures


class ClientCreateException(Exception):
    def __init__(self, client_name):
        super().__init__(f'Could not create client {client_name}')


class WrongClient:
    def __init__(self, client_name):
        self.client_name = client_name

    def __getattr__(self, member):
        raise ClientCreateException(self.client_name)


class _BaseAssetLaunchingTestCase(AssetLaunchingTestCase):

    assets_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'assets')
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chatd = cls.make_chatd()
        cls.auth = cls.make_auth()
        cls.create_token()
        cls.wait_strategy.wait(cls)

    @classmethod
    def start_auth_service(cls):
        cls.start_service('auth')
        cls.auth = cls.make_auth()
        until.true(cls.auth.is_up, tries=5)
        cls.create_token()

    @classmethod
    def stop_auth_service(cls):
        cls.stop_service('auth')

    @classmethod
    def start_chatd_service(cls):
        cls.start_service('chatd')
        cls.chatd = cls.make_chatd()

    @classmethod
    def stop_chatd_service(cls):
        cls.stop_service('chatd')

    @classmethod
    def create_token(cls):
        if isinstance(cls.auth, WrongClient):
            return

        token = MockUserToken(
            str(TOKEN_UUID),
            str(TOKEN_USER_UUID),
            metadata={
                'uuid': str(TOKEN_USER_UUID),
                'tenant_uuid': str(TOKEN_TENANT_UUID),
            },
        )
        cls.auth.set_token(token)
        credential = MockCredentials('chatd-service', 'chatd-password')
        cls.auth.set_valid_credentials(credential, str(TOKEN_UUID))
        cls.auth.set_tenants(
            {
                'uuid': str(TOKEN_TENANT_UUID),
                'name': 'name1',
                'parent_uuid': str(TOKEN_TENANT_UUID),
            },
            {
                'uuid': str(TOKEN_SUBTENANT_UUID),
                'name': 'name2',
                'parent_uuid': str(TOKEN_TENANT_UUID),
            },
        )

    @classmethod
    def make_db_session(cls):
        try:
            port = cls.service_port(5432, 'postgres')
        except (NoSuchService, NoSuchPort):
            return WrongClient('postgres')

        init_db(DB_URI.format(port=port), echo=DB_ECHO)
        return Session

    @classmethod
    def make_chatd(cls, token=str(TOKEN_UUID)):
        try:
            port = cls.service_port(9304, 'chatd')
        except (NoSuchService, NoSuchPort):
            return WrongClient('chatd')
        return ChatdClient(
            '127.0.0.1',
            port=port,
            prefix=None,
            https=False,
            token=token,
        )

    @classmethod
    def make_amid(cls):
        try:
            port = cls.service_port(9491, 'amid')
        except (NoSuchService, NoSuchPort):
            return WrongClient('amid')
        return AmidClient('127.0.0.1', port=port)

    @classmethod
    def make_auth(cls):
        try:
            port = cls.service_port(9497, 'auth')
        except (NoSuchService, NoSuchPort):
            return WrongClient('auth')
        return AuthClient('127.0.0.1', port=port)

    @classmethod
    def make_confd(cls):
        try:
            port = cls.service_port(9486, 'confd')
        except NoSuchService:
            return WrongClient('confd')
        return ConfdClient('127.0.0.1', port=port)

    @classmethod
    def make_bus(cls):
        try:
            port = cls.service_port(5672, 'rabbitmq')
        except NoSuchService:
            return WrongClient('rabbitmq')
        return BusClient.from_connection_fields(host='127.0.0.1', port=port)


class APIAssetLaunchingTestCase(_BaseAssetLaunchingTestCase):
    asset = 'base'
    service = 'chatd'
    wait_strategy = EverythingOkWaitStrategy()


class InitAssetLaunchingTestCase(_BaseAssetLaunchingTestCase):
    asset = 'initialization'
    service = 'chatd'
    wait_strategy = PresenceInitOkWaitStrategy()


class DBAssetLaunchingTestCase(_BaseAssetLaunchingTestCase):
    asset = 'database'
    service = 'postgresql'
    wait_strategy = NoWaitStrategy()


class _BaseIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._Session = DBAssetLaunchingTestCase.make_db_session()

    @property
    def _session(self):
        return self._Session()

    def setUp(self):
        super().setUp()
        self._dao = DAO()
        self._dao.tenant.find_or_create(TOKEN_TENANT_UUID)
        self._dao.tenant.find_or_create(TOKEN_SUBTENANT_UUID)
        self._session.commit()

    def tearDown(self):
        self._Session.rollback()
        self._Session.remove()


class DBIntegrationTest(_BaseIntegrationTest):
    pass


class APIIntegrationTest(_BaseIntegrationTest):
    @classmethod
    def setUpClass(cls):
        cls.reset_clients()

    @classmethod
    def reset_clients(cls):
        cls._Session = APIAssetLaunchingTestCase.make_db_session()
        cls.amid = APIAssetLaunchingTestCase.make_amid()
        cls.chatd = APIAssetLaunchingTestCase.make_chatd()
        cls.auth = APIAssetLaunchingTestCase.make_auth()
        cls.confd = APIAssetLaunchingTestCase.make_confd()
        cls.bus = APIAssetLaunchingTestCase.make_bus()
