# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid
import unittest

from mock import Mock

from hamcrest import (
    assert_that,
    has_entries,
)

from ..schemas import (
    UserPresenceSchema,
    LinePresenceSchema,
)

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
            uuid=UUID,
            tenant_uuid=UUID,
            sessions=[],
            lines=[]
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

        result = self.schema().dump(self.user).data
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

        result = self.schema().dump(self.user).data
        assert_that(result, has_entries(line_state='holding'))

    def test_set_line_state_talking(self):
        self.user.lines = [
            self.line_unavailable,
            self.line_available,
            self.line_talking,
            self.line_available,
            self.line_unavailable,
        ]

        result = self.schema().dump(self.user).data
        assert_that(result, has_entries(line_state='talking'))

    def test_set_line_state_available(self):
        self.user.lines = [
            self.line_unavailable,
            self.line_available,
            self.line_unavailable,
        ]

        result = self.schema().dump(self.user).data
        assert_that(result, has_entries(line_state='available'))

    def test_set_line_state_unavailable(self):
        self.user.lines = [
            self.line_unavailable,
        ]

        result = self.schema().dump(self.user).data
        assert_that(result, has_entries(line_state='unavailable'))


class TestLinePresenceSchema(unittest.TestCase):

    schema = LinePresenceSchema

    def setUp(self):
        self.line = Mock(id=1)

    def test_set_default_state(self):
        self.line.state = 'ringing'

        result = self.schema().dump(self.line).data
        assert_that(result, has_entries(state='ringing'))

    def test_set_default_state_when_none(self):
        self.line.state = None

        result = self.schema().dump(self.line).data
        assert_that(result, has_entries(state='unavailable'))
