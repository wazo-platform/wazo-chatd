# Copyright 2019-2020 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os
import uuid

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

logging.getLogger('amqp').setLevel(logging.INFO)
logging.getLogger('stevedore.extension').setLevel(logging.INFO)

DB_URI = 'postgresql://wazo-chatd:Secr7t@localhost:{port}'
DB_ECHO = os.getenv('DB_ECHO', '').lower() == 'true'

CHATD_TOKEN_TENANT_UUID = uuid.UUID('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeee1')

TOKEN_UUID = uuid.UUID('00000000-0000-0000-0000-000000000101')
TOKEN_TENANT_UUID = uuid.UUID('00000000-0000-0000-0000-000000000201')
TOKEN_SUBTENANT_UUID = uuid.UUID('00000000-0000-0000-0000-000000000202')
TOKEN_USER_UUID = uuid.UUID('00000000-0000-0000-0000-000000000301')

UNKNOWN_UUID = uuid.UUID('00000000-0000-0000-0000-000000000000')
WAZO_UUID = uuid.UUID('00000000-0000-0000-0000-0000000c4a7d')

logger = logging.getLogger(__name__)


class ClientCreateException(Exception):
    def __init__(self, client_name):
        super().__init__(f'Could not create client {client_name}')


class WrongClient:
    def __init__(self, client_name):
        self.client_name = client_name

    def __getattr__(self, member):
        raise ClientCreateException(self.client_name)


class BaseIntegrationTest(AssetLaunchingTestCase):

    assets_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'assets')
    )
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
        cls.auth.set_tenants(
            {
                'uuid': str(CHATD_TOKEN_TENANT_UUID),
                'name': 'chatd-token',
                'parent_uuid': str(CHATD_TOKEN_TENANT_UUID),
            },
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
    def reset_clients(cls):
        cls.amid = cls.make_amid()
        cls.chatd = cls.make_chatd()
        cls.auth = cls.make_auth()
        cls.confd = cls.make_confd()
        cls.bus = cls.make_bus()

    @classmethod
    def make_chatd(cls, token=str(TOKEN_UUID)):
        try:
            port = cls.service_port(9304, 'chatd')
        except NoSuchService:
            return WrongClient('chatd')
        return ChatdClient(
            'localhost', port=port, token=token, verify_certificate=False
        )

    @classmethod
    def make_amid(cls):
        try:
            port = cls.service_port(9491, 'amid')
        except (NoSuchService, NoSuchPort):
            return WrongClient('amid')
        return AmidClient('localhost', port=port)

    @classmethod
    def make_auth(cls):
        try:
            port = cls.service_port(9497, 'auth')
        except NoSuchService:
            return WrongClient('auth')
        return AuthClient('localhost', port=port)

    @classmethod
    def make_confd(cls):
        try:
            port = cls.service_port(9486, 'confd')
        except NoSuchService:
            return WrongClient('confd')
        return ConfdClient('localhost', port=port)

    @classmethod
    def make_bus(cls):
        try:
            port = cls.service_port(5672, 'rabbitmq')
        except NoSuchService:
            return WrongClient('rabbitmq')
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
