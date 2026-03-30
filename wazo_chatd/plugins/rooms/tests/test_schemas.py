# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
import uuid
from unittest.mock import MagicMock

from hamcrest import assert_that, calling, has_entries, has_length, not_, raises
from xivo.mallow_helpers import ValidationError

from ..schemas import (
    ListRequestSchema,
    MessageListRequestSchema,
    MessageSchema,
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


class TestMessageSchemaType(unittest.TestCase):
    def test_type_defaults_to_internal_when_no_meta(self) -> None:
        message = MagicMock(meta=None)

        result = MessageSchema().dump(message)

        assert result['type'] == 'internal'

    def test_type_from_meta(self) -> None:
        message = MagicMock()
        message.meta.type_ = 'sms'
        message.meta.backend = 'twilio'

        result = MessageSchema().dump(message)

        assert result['type'] == 'sms'
        assert result['backend'] == 'twilio'

    def test_backend_none_when_no_meta(self) -> None:
        message = MagicMock(meta=None)

        result = MessageSchema().dump(message)

        assert result['backend'] is None


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
