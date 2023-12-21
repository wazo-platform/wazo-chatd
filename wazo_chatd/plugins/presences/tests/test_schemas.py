# Copyright 2019-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
import uuid
from unittest.mock import MagicMock, Mock

from hamcrest import (
    assert_that,
    calling,
    contains,
    contains_inanyorder,
    empty,
    has_entries,
    raises,
)
from marshmallow.exceptions import ValidationError

from ..schemas import LinePresenceSchema, ListRequestSchema, UserPresenceSchema

UUID = uuid.uuid4()


class TestUserPresenceSchema(unittest.TestCase):
    schema = UserPresenceSchema

    def setUp(self):
        self.line_ringing = Mock(
            id=1, channels_state=['ringing'], endpoint_state='available'
        )
        self.line_holding = Mock(
            id=2, channels_state=['holding'], endpoint_state='available'
        )
        self.line_talking = Mock(
            id=3, channels_state=['talking'], endpoint_state='available'
        )
        self.line_available = Mock(
            id=4, channels_state=['undefined'], endpoint_state='available'
        )
        self.line_unavailable = Mock(
            id=5, channels_state=['undefined'], endpoint_state='unavailable'
        )
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
        self.line = Mock(id=42, channels_state=[], endpoint_state=None)

    def test_set_state_ringing(self):
        self.line.channels_state = [
            'undefined',
            'talking',
            'holding',
            'ringing',
            'holding',
            'talking',
            'undefined',
        ]

        result = self.schema().dump(self.line)
        assert_that(result, has_entries(state='ringing'))

    def test_set_state_holding(self):
        self.line.channels_state = [
            'undefined',
            'talking',
            'holding',
            'talking',
            'undefined',
        ]

        result = self.schema().dump(self.line)
        assert_that(result, has_entries(state='holding'))

    def test_set_state_talking(self):
        self.line.channels_state = [
            'undefined',
            'talking',
            'undefined',
        ]

        result = self.schema().dump(self.line)
        assert_that(result, has_entries(state='talking'))

    def test_set_state_to_endpoint_state(self):
        self.line.endpoint_state = 'available'
        self.line.channels_state = ['undefined']

        result = self.schema().dump(self.line)
        assert_that(result, has_entries(state='available'))

    def test_set_state_default_to_unavalaible(self):
        self.line.endpoint_state = None
        self.line.channels_state = []

        result = self.schema().dump(self.line)
        assert_that(result, has_entries(state='unavailable'))


class TestListRequestSchema(unittest.TestCase):
    schema = ListRequestSchema

    def setUp(self):
        self.request_args = MagicMock()
        self.request_args.to_dict.return_value = {}

    def test_get_user_uuid(self):
        uuid_1 = uuid.uuid4()
        self.request_args.get.return_value = str(uuid_1)
        self.request_args.__getitem__.return_value = str(uuid_1)

        result = self.schema().load(self.request_args)
        assert_that(result, has_entries(uuids=contains(uuid_1)))

    def test_get_user_uuid_multiple(self):
        uuid_1 = uuid.uuid4()
        uuid_2 = uuid.uuid4()
        user_uuid = f'{uuid_1},{uuid_2}'
        self.request_args.get.return_value = user_uuid
        self.request_args.__getitem__.return_value = user_uuid

        result = self.schema().load(self.request_args)
        assert_that(result, has_entries(uuids=contains_inanyorder(uuid_1, uuid_2)))

    def test_get_user_uuid_empty(self):
        self.request_args.get.return_value = ''

        result = self.schema().load(self.request_args)
        assert_that(result, has_entries(uuids=empty()))

    def test_get_user_uuid_with_wrong_ending(self):
        uuid_1 = uuid.uuid4()
        user_uuid = f'{uuid_1},'
        self.request_args.get.return_value = user_uuid
        self.request_args.__getitem__.return_value = user_uuid

        assert_that(
            calling(self.schema().load).with_args(self.request_args),
            raises(ValidationError),
        )
