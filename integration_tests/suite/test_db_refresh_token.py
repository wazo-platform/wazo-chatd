# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import assert_that, calling, equal_to, has_items

from wazo_chatd.exceptions import UnknownRefreshTokenException
from xivo_test_helpers.hamcrest.raises import raises

from .helpers import fixtures
from .helpers.base import BaseIntegrationTest
from .helpers.wait_strategy import NoWaitStrategy

TENANT_UUID = str(uuid.uuid4())
USER_UUID = str(uuid.uuid4())
UNKNOWN_UUID = str(uuid.uuid4())


class TestRefreshToken(BaseIntegrationTest):

    asset = 'database'
    service = 'postgresql'
    wait_strategy = NoWaitStrategy()

    @fixtures.db.refresh_token()
    def test_get(self, refresh_token):
        result = self._dao.refresh_token.get(refresh_token.user_uuid, refresh_token.client_id)
        assert_that(result, equal_to(refresh_token))

        assert_that(
            calling(self._dao.refresh_token.get).with_args(UNKNOWN_UUID, refresh_token.client_id),
            raises(UnknownRefreshTokenException),
        )

        assert_that(
            calling(self._dao.refresh_token.get).with_args(refresh_token.user_uuid, 'unknown'),
            raises(UnknownRefreshTokenException),
        )

    @fixtures.db.refresh_token()
    @fixtures.db.refresh_token()
    def test_list(self, refresh_token_1, refresh_token_2):
        refresh_tokens = self._dao.refresh_token.list_()
        assert_that(refresh_tokens, has_items(refresh_token_1, refresh_token_2))

    @fixtures.db.tenant(uuid=TENANT_UUID)
    @fixtures.db.user(uuid=USER_UUID, tenant_uuid=TENANT_UUID)
    @fixtures.db.refresh_token(user_uuid=USER_UUID)
    def test_tenant_uuid(self, tenant, _, refresh_token):
        assert_that(refresh_token.tenant_uuid, equal_to(tenant.uuid))

    @fixtures.db.refresh_token(mobile=False)
    def test_update(self, refresh_token):
        mobile = True
        refresh_token.mobile = mobile
        self._dao.refresh_token.update(refresh_token)

        self._session.expire_all()
        assert_that(refresh_token.mobile, equal_to(mobile))
