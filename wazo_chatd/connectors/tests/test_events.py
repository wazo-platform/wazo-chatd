# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest

from wazo_chatd.connectors.events import MessageDeliveryStatusEvent


class TestMessageDeliveryStatusEvent(unittest.TestCase):
    def test_event_name(self) -> None:
        event = MessageDeliveryStatusEvent(
            delivery_data={'status': 'sent', 'message_uuid': 'msg-1'},
            tenant_uuid='tenant-1',
            user_uuids=['user-1'],
            room_uuid='room-1',
            message_uuid='msg-1',
        )

        assert event.name == 'chatd_message_delivery_status'

    def test_routing_key(self) -> None:
        event = MessageDeliveryStatusEvent(
            delivery_data={'status': 'sent', 'message_uuid': 'msg-1'},
            tenant_uuid='tenant-1',
            user_uuids=['user-1'],
            room_uuid='room-1',
            message_uuid='msg-1',
        )

        assert event.routing_key == 'chatd.rooms.room-1.messages.msg-1.delivery'

    def test_content_is_delivery_data(self) -> None:
        data = {'status': 'failed', 'message_uuid': 'msg-1', 'reason': 'timeout'}
        event = MessageDeliveryStatusEvent(
            delivery_data=data,
            tenant_uuid='tenant-1',
            user_uuids=['user-1', 'user-2'],
            room_uuid='room-1',
            message_uuid='msg-1',
        )

        assert event.content == data
