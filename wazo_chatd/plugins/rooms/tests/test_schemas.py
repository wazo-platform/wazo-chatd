# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest

from hamcrest import (
    any_of,
    assert_that,
    has_entries,
    has_key,
    not_,
)

from ..schemas import ListRequestSchema


class TestListRequestSchema(unittest.TestCase):

    schema = ListRequestSchema

    def test_load_direction_missing(self):
        result = self.schema().load({}).data
        assert_that(result, has_entries(direction='desc'))

    def test_load_not_implemented(self):
        result = self.schema().load({}).data
        assert_that(result, not_(any_of(
            has_key('offset'),
            has_key('search'),
            has_key('limit'),
        )))

    def test_load_order_default(self):
        result = self.schema().load({}).data
        assert_that(result, has_entries(order='created_at'))
