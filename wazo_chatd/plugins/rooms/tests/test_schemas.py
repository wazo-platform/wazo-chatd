# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import unittest
import uuid
from unittest.mock import MagicMock, Mock

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


class TestMessageSchemaDelivery(unittest.TestCase):
    def test_internal_message_has_delivery_with_delivered_status(self) -> None:
        message = Mock(
            meta=None,
            spec=[
                'uuid',
                'content',
                'alias',
                'user_uuid',
                'tenant_uuid',
                'wazo_uuid',
                'created_at',
                'room',
                'meta',
            ],
        )

        result = MessageSchema().dump(message)

        assert result['delivery'] == {
            'type': 'internal',
            'backend': None,
            'status': 'delivered',
        }

    def test_connector_message_has_delivery_from_meta(self) -> None:
        meta = Mock(type_='sms', backend='twilio', status='sent')
        message = Mock(meta=meta)

        result = MessageSchema().dump(message)

        assert result['delivery'] == {
            'type': 'sms',
            'backend': 'twilio',
            'status': 'sent',
        }

    def test_connector_message_with_null_status(self) -> None:
        meta = Mock(type_='sms', backend='twilio', status=None)
        message = Mock(meta=meta)

        result = MessageSchema().dump(message)

        assert result['delivery']['status'] is None


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
