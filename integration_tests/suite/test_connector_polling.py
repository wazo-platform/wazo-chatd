# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

from wazo_test_helpers import until

from wazo_chatd.database.models import MessageMeta, RoomMessage

from .helpers import fixtures
from .helpers.base import PollingConnectorIntegrationTest, use_asset

USER_UUID_1 = uuid.uuid4()


@use_asset('connectors_polling')
class TestPollingInbound(PollingConnectorIntegrationTest):
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.http.user_identity(
        user_uuid=USER_UUID_1,
        identity='test:+15551234',
    )
    def test_scan_inbound_creates_message(self, user, identity):
        self.connector_mock.set_scan(
            {
                'from': 'test:+15559876',
                'to': 'test:+15551234',
                'body': 'polled hello',
                'message_id': 'ext-poll-001',
                'type': 'test',
            }
        )

        def message_persisted():
            message = (
                self._session.query(RoomMessage)
                .filter(RoomMessage.content == 'polled hello')
                .first()
            )
            assert message is not None
            meta = (
                self._session.query(MessageMeta)
                .filter(MessageMeta.message_uuid == message.uuid)
                .first()
            )
            assert meta is not None
            assert meta.backend == 'test'
            assert len(meta.deliveries) == 1
            assert meta.deliveries[0].external_id == 'ext-poll-001'

        until.assert_(message_persisted, timeout=10, interval=0.2)


@use_asset('connectors_polling')
class TestPollingOutboundTracking(PollingConnectorIntegrationTest):
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.http.user_identity(
        user_uuid=USER_UUID_1,
        identity='test:+15551234',
    )
    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1}],
        messages=[
            {
                'content': 'outbound hello',
                'meta': {'type_': 'test', 'backend': 'test'},
                'deliveries': [
                    {'external_id': 'ext-out-001', 'statuses': ['accepted']}
                ],
            }
        ],
    )
    def test_track_outbound_records_terminal_status(self, user, identity, room):
        message = room.messages[0]

        self.connector_mock.set_track('ext-out-001', {'status': 'delivered'})

        self.assert_delivery_status(message.uuid, 'delivered', timeout=10)

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.http.user_identity(
        user_uuid=USER_UUID_1,
        identity='test:+15551234',
    )
    @fixtures.db.room(
        users=[{'uuid': USER_UUID_1}],
        messages=[
            {
                'content': 'will fail',
                'meta': {'type_': 'test', 'backend': 'test'},
                'deliveries': [
                    {'external_id': 'ext-out-fail', 'statuses': ['accepted']}
                ],
            }
        ],
    )
    def test_track_outbound_records_failed_status(self, user, identity, room):
        message = room.messages[0]

        self.connector_mock.set_track('ext-out-fail', {'status': 'failed'})

        self.assert_delivery_status(message.uuid, 'failed', timeout=10)
