# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from wazo_chatd_client import Client as ChatdClient
from wazo_chatd.database.queries.user import UserDAO
from wazo_chatd.database.queries.tenant import TenantDAO

from xivo_test_helpers.asset_launching_test_case import AssetLaunchingTestCase, NoSuchService

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

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._Session = scoped_session(sessionmaker())
        engine = create_engine(DB_URI.format(port=cls.service_port(5432, 'postgres')), echo=DB_ECHO)
        cls._Session.configure(bind=engine)
        cls.chatd = cls.make_chatd(VALID_TOKEN)

    @classmethod
    def make_chatd(cls, token):
        try:
            port = cls.service_port(9304, 'chatd')
        except NoSuchService as e:
            logger.debug(e)
            return
        return ChatdClient(
            'localhost',
            port=port,
            token=token,
            verify_certificate=False,
        )

    def setUp(self):
        super().setUp()
        self._session = self._Session()

        TenantDAO.session = self._session
        self._tenant_dao = TenantDAO()
        self._tenant_dao.find_or_create(MASTER_TENANT_UUID)
        self._tenant_dao.find_or_create(SUBTENANT_UUID)

        UserDAO.session = self._session
        self._user_dao = UserDAO()

    def tearDown(self):
        self._Session.rollback()
        self._Session.remove()
