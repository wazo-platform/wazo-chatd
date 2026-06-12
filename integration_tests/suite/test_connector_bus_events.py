# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

from wazo_test_helpers import until

from wazo_chatd.plugin_helpers.tenant import make_uuid5

from .helpers import fixtures
from .helpers.base import (
    TOKEN_TENANT_UUID,
    TOKEN_USER_UUID,
    ConnectorIntegrationTest,
    use_asset,
)

EXTERNAL_IDENTITY = 'test:+15559876'
SENDER_IDENTITY = 'test:+15551234'
RECIPIENT_UUID = uuid.uuid4()
OTHER_TENANT_UUID = uuid.uuid4()
FOREIGN_USER_UUID = uuid.uuid4()


@use_asset('connectors')
class TestOutboundMessageEvent(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity=SENDER_IDENTITY,
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_outbound_message_emits_event_with_type_and_backend(
        self, user, identity, room
    ):
        accumulator = self.bus.accumulator(
            headers={'name': 'chatd_user_room_message_created'}
        )

        self.connector_mock.reset()
        self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'Outbound event', 'sender_identity_uuid': str(identity.uuid)},
        )

        def event_received():
            events = accumulator.accumulate(with_headers=True)
            matching = [
                e
                for e in events
                if e['message']['data'].get('content') == 'Outbound event'
            ]
            assert len(matching) >= 1
            data = matching[0]['message']['data']
            delivery = data['delivery']
            assert delivery['type'] == 'test'
            assert delivery['backend'] == 'test'

        until.assert_(event_received, timeout=5, interval=0.1)


@use_asset('connectors')
class TestInboundMessageEvent(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity=SENDER_IDENTITY,
    )
    def test_inbound_webhook_emits_message_event_with_delivery(self, user, identity):
        accumulator = self.bus.accumulator(
            headers={'name': 'chatd_user_room_message_created'}
        )

        response = self.post_inbound(
            {
                'from': EXTERNAL_IDENTITY,
                'to': SENDER_IDENTITY,
                'body': 'Inbound event test',
                'message_id': f'ext-bus-{uuid.uuid4()}',
            }
        )
        assert response.status_code == 204

        def event_received():
            events = accumulator.accumulate(with_headers=True)
            assert len(events) >= 1
            data = events[0]['message']['data']
            assert data['content'] == 'Inbound event test'
            delivery = data['delivery']
            assert delivery['type'] == 'test'
            assert delivery['backend'] == 'test'

        until.assert_(event_received, timeout=5, interval=0.1)

    @fixtures.db.tenant(uuid=OTHER_TENANT_UUID)
    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user(uuid=FOREIGN_USER_UUID, tenant_uuid=OTHER_TENANT_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity=SENDER_IDENTITY,
    )
    @fixtures.db.user_identity(
        user_uuid=FOREIGN_USER_UUID,
        tenant_uuid=OTHER_TENANT_UUID,
        backend='test',
        identity=EXTERNAL_IDENTITY,
    )
    def test_cross_tenant_inbound_event_targets_synthetic_sender(
        self, foreign_tenant, recipient, sender, recipient_identity, sender_identity
    ):
        accumulator = self.bus.accumulator(
            headers={'name': 'chatd_user_room_message_created'}
        )

        response = self.post_inbound(
            {
                'from': EXTERNAL_IDENTITY,
                'to': SENDER_IDENTITY,
                'body': 'Cross-tenant event test',
                'message_id': f'ext-bus-cross-{uuid.uuid4()}',
            }
        )
        assert response.status_code == 204

        synthetic_uuid = str(make_uuid5(str(TOKEN_TENANT_UUID), EXTERNAL_IDENTITY))

        def event_targets_external_sender():
            events = accumulator.accumulate(with_headers=True)
            relevant = [
                e
                for e in events
                if e['message']['data']['content'] == 'Cross-tenant event test'
            ]
            assert relevant
            targeted = {
                key.split(':', 1)[1]
                for event in relevant
                for key in event['headers']
                if key.startswith('user_uuid:')
            }
            assert synthetic_uuid in targeted
            assert str(TOKEN_USER_UUID) in targeted
            assert str(FOREIGN_USER_UUID) not in targeted

        until.assert_(event_targets_external_sender, timeout=5, interval=0.1)


@use_asset('connectors')
class TestDeliveryStatusEvent(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity=SENDER_IDENTITY,
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_delivery_status_emits_event(self, user, identity, room):
        accumulator = self.bus.accumulator(
            headers={'name': 'chatd_message_delivery_status'}
        )

        self.connector_mock.reset()
        self.connector_mock.set_config(
            send_behavior='succeed', external_id='ext-bus-status-001'
        )

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'Track delivery', 'sender_identity_uuid': str(identity.uuid)},
        )

        def accepted_event_received():
            events = accumulator.accumulate(with_headers=True)
            accepted = [
                e for e in events if e['message']['data'].get('status') == 'accepted'
            ]
            assert len(accepted) >= 1
            data = accepted[0]['message']['data']
            assert data['message_uuid'] == message['uuid']
            assert data['backend'] == 'test'
            assert data['recipient_identity']

        until.assert_(accepted_event_received, timeout=5, interval=0.1)

        self.post_inbound(
            {
                'external_id': 'ext-bus-status-001',
                'status': 'delivered',
            }
        )

        def delivered_event_received():
            events = accumulator.accumulate(with_headers=True)
            delivered = [
                e for e in events if e['message']['data'].get('status') == 'delivered'
            ]
            assert len(delivered) >= 1
            data = delivered[0]['message']['data']
            assert data['message_uuid'] == message['uuid']

        until.assert_(delivered_event_received, timeout=5, interval=0.1)


@use_asset('connectors')
class TestExternalAuthCacheInvalidation(ConnectorIntegrationTest):
    def setUp(self):
        super().setUp()
        self.addCleanup(
            self.auth.set_external_config,
            {'test': {'mock_url': 'http://connector-mock:8080'}},
        )

    def test_deleted_event_invalidates_cache(self):
        connectors = self.chatd.connectors.list()
        test_connector = next(c for c in connectors['items'] if c['name'] == 'test')
        assert test_connector['configured'] is True

        self.auth.set_external_config({})

        self.bus.send_tenant_external_auth_deleted_event(TOKEN_TENANT_UUID, 'test')

        def cache_invalidated():
            result = self.chatd.connectors.list()
            test_connector = next(c for c in result['items'] if c['name'] == 'test')
            assert test_connector['configured'] is False

        until.assert_(cache_invalidated, timeout=5, interval=0.1)
