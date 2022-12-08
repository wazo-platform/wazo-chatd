# Copyright 2019-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid
import unittest

from unittest.mock import MagicMock

from hamcrest import (
    assert_that,
    calling,
    has_entries,
    has_length,
    not_,
    raises,
)
from xivo.mallow_helpers import ValidationError

from ..schemas import (
    ListRequestSchema,
    MessageListRequestSchema,
    RoomListRequestSchema,
)


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


class TestRoomListRequestSchema(unittest.TestCase):

    schema = RoomListRequestSchema

    # WAZO-2953: non-regression
    def test_missing_value_is_not_reused(self):
        args_dict = MagicMock(return_value={})
        args_dict.__getitem__.side_effect = {}.__getitem__
        args = MagicMock(to_dict=args_dict)
        args.get.return_value = {}

        result = self.schema().load(args)
        result['user_uuids'].append(uuid.uuid4())

        result = self.schema().load(args)
        assert_that(result['user_uuids'], has_length(0))
