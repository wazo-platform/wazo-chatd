# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest

from hamcrest import assert_that, calling, has_entries, not_, raises
from xivo.mallow_helpers import ValidationError

from ..schemas import ListRequestSchema, MessageListRequestSchema


class TestListRequestSchema(unittest.TestCase):

    schema = ListRequestSchema

    def test_load_direction_missing(self):
        result = self.schema().load({})
        assert_that(result, has_entries(direction='desc'))

    def test_load_order_default(self):
        result = self.schema().load({})
        assert_that(result, has_entries(order='created_at'))


class TestMessageListRequestSchema(unittest.TestCase):

    schema = MessageListRequestSchema

    def test_search_or_distinct_missing(self):
        assert_that(
            calling(self.schema().load).with_args({}),
            raises(ValidationError, pattern='search or distinct'),
        )
        assert_that(
            calling(self.schema().load).with_args({'search': 'ok'}),
            not_(raises(ValidationError, pattern='search or distinct')),
        )
