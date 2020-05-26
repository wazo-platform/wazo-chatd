# Copyright 2019-2020 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from hamcrest import (
    assert_that,
    calling,
    contains,
    contains_inanyorder,
    empty,
    equal_to,
    has_items,
    has_properties,
)

from wazo_chatd.database.models import Channel
from wazo_chatd.exceptions import UnknownLineException
from xivo_test_helpers.hamcrest.raises import raises

from .helpers import fixtures
from .helpers.base import BaseIntegrationTest
from .helpers.wait_strategy import NoWaitStrategy

TENANT_UUID = uuid.uuid4()
USER_UUID = uuid.uuid4()
UNKNOWN_ID = 0


class TestLine(BaseIntegrationTest):

    asset = 'database'
    service = 'postgresql'
    wait_strategy = NoWaitStrategy()

    @fixtures.db.line()
    def test_get(self, line):
        result = self._dao.line.get(line.id)
        assert_that(result, equal_to(line))

        assert_that(
            calling(self._dao.line.get).with_args(UNKNOWN_ID),
            raises(UnknownLineException),
        )

    @fixtures.db.line()
    @fixtures.db.line()
    def test_find(self, line, _):
        result = self._dao.line.find(line.id)
        assert_that(result, equal_to(line))

        result = self._dao.line.find(UNKNOWN_ID)
        assert_that(result, equal_to(None))

    @fixtures.db.line()
    @fixtures.db.line()
    def test_find_by(self, line, _):
        result = self._dao.line.find_by(endpoint_name=line.endpoint_name)
        assert_that(result, equal_to(line))

        result = self._dao.line.find_by(endpoint_name='unknown')
        assert_that(result, equal_to(None))

    @fixtures.db.line()
    @fixtures.db.line()
    def test_list(self, line_1, line_2):
        lines = self._dao.line.list_()
        assert_that(lines, has_items(line_1, line_2))

    @fixtures.db.tenant(uuid=TENANT_UUID)
    @fixtures.db.user(uuid=USER_UUID, tenant_uuid=TENANT_UUID)
    @fixtures.db.line(user_uuid=USER_UUID)
    def test_tenant_uuid(self, tenant, _, line):
        assert_that(line.tenant_uuid, equal_to(tenant.uuid))

    @fixtures.db.endpoint(name='SIP/custom-name')
    @fixtures.db.line(endpoint_name='SIP/custom-name')
    def test_state(self, endpoint, line):
        assert_that(line.state, equal_to(endpoint.state))

    @fixtures.db.line(id=1)
    @fixtures.db.channel(line_id=1, state='talking')
    @fixtures.db.channel(line_id=1, state='holding')
    def test_channels_state(self, line, channel_1, channel_2):
        assert_that(line.channels_state, contains_inanyorder('talking', 'holding'))

    @fixtures.db.line(media='audio')
    def test_update(self, line):
        line.media = 'video'
        self._dao.line.update(line)

        self._session.expire_all()
        assert_that(line.media, equal_to('video'))

    @fixtures.db.endpoint()
    @fixtures.db.line()
    def test_associate_endpoint(self, endpoint, line):
        self._dao.line.associate_endpoint(line, endpoint)

        self._session.expire_all()
        assert_that(line.endpoint, equal_to(endpoint))

    @fixtures.db.endpoint(name='endpoint-name')
    @fixtures.db.line(endpoint_name='endpoint-name')
    def test_dissociate_endpoint(self, endpoint, line):
        self._dao.line.dissociate_endpoint(line)

        self._session.expire_all()
        assert_that(line.endpoint, equal_to(None))

    @fixtures.db.line()
    def test_add_channel(self, line):
        channel_name = 'channel-name'
        channel = Channel(name=channel_name)
        self._dao.line.add_channel(line, channel)

        self._session.expire_all()
        assert_that(line.channels, contains(has_properties(name=channel_name)))

        # twice
        self._dao.line.add_channel(line, channel)

        self._session.expire_all()
        assert_that(line.channels, contains(has_properties(name=channel_name)))

    @fixtures.db.line(id=1)
    @fixtures.db.channel(line_id=1)
    def test_remove_channel(self, line, channel):
        self._dao.line.remove_channel(line, channel)

        self._session.expire_all()
        assert_that(line.channels, empty())

        # twice
        self._dao.line.remove_channel(line, channel)

        self._session.expire_all()
        assert_that(line.channels, empty())
