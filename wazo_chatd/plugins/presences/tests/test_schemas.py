# Copyright 2019-2020 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid
import unittest

from mock import MagicMock, Mock

from hamcrest import assert_that, contains, empty, has_entries

from ..schemas import UserPresenceSchema, LinePresenceSchema, ListRequestSchema

UUID = str(uuid.uuid4())


class TestUserPresenceSchema(unittest.TestCase):

    schema = UserPresenceSchema

    def setUp(self):
        self.line_ringing = Mock(id=1, state='ringing')
        self.line_holding = Mock(id=2, state='holding')
        self.line_talking = Mock(id=3, state='talking')
        self.line_available = Mock(id=4, state='available')
        self.line_unavailable = Mock(id=5, state='unavailable')
        self.user = Mock(
            uuid=UUID, tenant_uuid=UUID, sessions=[], lines=[], refresh_tokens=[]
        )

    def test_set_line_state_ringing(self):
        self.user.lines = [
            self.line_unavailable,
            self.line_available,
            self.line_talking,
            self.line_holding,
            self.line_ringing,
            self.line_holding,
            self.line_talking,
            self.line_available,
            self.line_unavailable,
        ]

        result = self.schema().dump(self.user)
        assert_that(result, has_entries(line_state='ringing'))

    def test_set_line_state_holding(self):
        self.user.lines = [
            self.line_unavailable,
            self.line_available,
            self.line_talking,
            self.line_holding,
            self.line_talking,
            self.line_available,
            self.line_unavailable,
        ]

        result = self.schema().dump(self.user)
        assert_that(result, has_entries(line_state='holding'))

    def test_set_line_state_talking(self):
        self.user.lines = [
            self.line_unavailable,
            self.line_available,
            self.line_talking,
            self.line_available,
            self.line_unavailable,
        ]

        result = self.schema().dump(self.user)
        assert_that(result, has_entries(line_state='talking'))

    def test_set_line_state_available(self):
        self.user.lines = [
            self.line_unavailable,
            self.line_available,
            self.line_unavailable,
        ]

        result = self.schema().dump(self.user)
        assert_that(result, has_entries(line_state='available'))

    def test_set_line_state_unavailable(self):
        self.user.lines = [self.line_unavailable]

        result = self.schema().dump(self.user)
        assert_that(result, has_entries(line_state='unavailable'))

    def test_set_mobile_when_no_refresh_token_and_no_session(self):
        self.user.refresh_tokens = []
        self.user.sessions = []

        result = self.schema().dump(self.user)
        assert_that(result, has_entries(mobile=False))

    def test_set_mobile_when_no_refresh_token_and_false_session(self):
        self.user.refresh_tokens = []
        self.user.sessions = [Mock(uuid=UUID, mobile=False)]

        result = self.schema().dump(self.user)
        assert_that(result, has_entries(mobile=False))

    def test_set_mobile_when_no_refresh_token_and_true_session(self):
        self.user.refresh_tokens = []
        self.user.sessions = [Mock(uuid=UUID, mobile=True)]

        result = self.schema().dump(self.user)
        assert_that(result, has_entries(mobile=True))

    def test_set_mobile_when_false_refresh_token_and_no_session(self):
        self.user.refresh_tokens = [Mock(mobile=False)]
        self.user.sessions = []

        result = self.schema().dump(self.user)
        assert_that(result, has_entries(mobile=False))

    def test_set_mobile_when_true_refresh_token_and_no_session(self):
        self.user.refresh_tokens = [Mock(mobile=True)]
        self.user.sessions = []

        result = self.schema().dump(self.user)
        assert_that(result, has_entries(mobile=True))

    def test_set_mobile_when_false_refresh_token_and_true_session(self):
        self.user.refresh_tokens = [Mock(mobile=False)]
        self.user.sessions = [Mock(uuid=UUID, mobile=True)]

        result = self.schema().dump(self.user)
        assert_that(result, has_entries(mobile=True))

    def test_set_mobile_when_true_refresh_token_and_false_session(self):
        self.user.refresh_tokens = [Mock(mobile=True)]
        self.user.sessions = [Mock(uuid=UUID, mobile=False)]

        result = self.schema().dump(self.user)
        assert_that(result, has_entries(mobile=True))

    def test_set_mobile_when_false_refresh_token_and_false_session(self):
        self.user.refresh_tokens = [Mock(mobile=False)]
        self.user.sessions = [Mock(uuid=UUID, mobile=False)]

        result = self.schema().dump(self.user)
        assert_that(result, has_entries(mobile=False))


class TestLinePresenceSchema(unittest.TestCase):

    schema = LinePresenceSchema

    def setUp(self):
        self.line = Mock(id=1)

    def test_set_default_state(self):
        self.line.state = 'ringing'

        result = self.schema().dump(self.line)
        assert_that(result, has_entries(state='ringing'))

    def test_set_default_state_when_none(self):
        self.line.state = None

        result = self.schema().dump(self.line)
        assert_that(result, has_entries(state='unavailable'))


class TestListRequestSchema(unittest.TestCase):

    schema = ListRequestSchema

    def setUp(self):
        self.request_args = MagicMock()
        self.request_args.to_dict.return_value = {}

    def test_get_user_uuid(self):
        uuid_1 = str(uuid.uuid4())
        self.request_args.get.return_value = uuid_1
        self.request_args.__getitem__.return_value = uuid_1

        result = self.schema().load(self.request_args)
        assert_that(result, has_entries(uuids=contains(uuid_1)))

    def test_get_user_uuid_multiple(self):
        uuid_1 = str(uuid.uuid4())
        uuid_2 = str(uuid.uuid4())
        user_uuid = '{},{}'.format(uuid_1, uuid_2)
        self.request_args.get.return_value = user_uuid
        self.request_args.__getitem__.return_value = user_uuid

        result = self.schema().load(self.request_args)
        assert_that(result, has_entries(uuids=contains(uuid_1, uuid_2)))

    def test_get_user_uuid_empty(self):
        self.request_args.get.return_value = ''

        result = self.schema().load(self.request_args)
        assert_that(result, has_entries(uuids=empty()))
