# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

from wazo_test_helpers import until

from .helpers import fixtures
from .helpers.base import (
    TOKEN_TENANT_UUID,
    TOKEN_USER_UUID,
    ConnectorIntegrationTest,
    use_asset,
)
from .helpers.connector import status_update_payload

EXTERNAL_IDENTITY = 'test:+15559876'
SENDER_IDENTITY = 'test:+15551234'


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
            assert len(matching) == 1
            data = matching[0]['message']['data']
            delivery = data['delivery']
            assert delivery['type'] == 'test'
            assert delivery['backend'] == 'test'
            assert delivery['recipients'] == [EXTERNAL_IDENTITY]

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

        response = self.post_webhook(
            json={
                'from': EXTERNAL_IDENTITY,
                'to': SENDER_IDENTITY,
                'body': 'Inbound event test',
                'message_id': f'ext-bus-{uuid.uuid4()}',
            },
        )
        assert response.status_code == 204

        def event_received():
            events = accumulator.accumulate(with_headers=True)
            matching = [
                e
                for e in events
                if e['message']['data'].get('content') == 'Inbound event test'
            ]
            assert len(matching) == 1
            delivery = matching[0]['message']['data']['delivery']
            assert delivery['type'] == 'test'
            assert delivery['backend'] == 'test'

        until.assert_(event_received, timeout=5, interval=0.1)


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
            assert len(accepted) == 1
            data = accepted[0]['message']['data']
            assert data['message_uuid'] == message['uuid']
            assert data['backend'] == 'test'
            assert data['recipient_identity']

        until.assert_(accepted_event_received, timeout=5, interval=0.1)

        self.post_webhook(
            json=status_update_payload(
                external_id='ext-bus-status-001', status='delivered'
            ),
        )

        def delivered_event_received():
            events = accumulator.accumulate(with_headers=True)
            delivered = [
                e for e in events if e['message']['data'].get('status') == 'delivered'
            ]
            assert len(delivered) == 1
            data = delivered[0]['message']['data']
            assert data['message_uuid'] == message['uuid']
            assert data['backend'] == 'test'
            assert data['recipient_identity']

        until.assert_(delivered_event_received, timeout=5, interval=0.1)


@use_asset('connectors')
class TestUserIdentityEvents(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=TOKEN_USER_UUID, tenant_uuid=TOKEN_TENANT_UUID)
    def test_create_emits_event(self, user):
        accumulator = self.bus.accumulator(
            headers={'name': 'chatd_user_identity_created'}
        )

        result = self.chatd.user_identities.create(
            str(TOKEN_USER_UUID),
            {'backend': 'test', 'type': 'test', 'identity': 'test:bus-create'},
        )

        def event_received():
            events = accumulator.accumulate(with_headers=True)
            matching = [
                e for e in events if e['message']['data'].get('uuid') == result['uuid']
            ]
            assert len(matching) == 1
            data = matching[0]['message']['data']
            assert data['identity'] == 'test:bus-create'
            assert data['backend'] == 'test'
            assert data['type'] == 'test'
            assert data['user_uuid'] == str(TOKEN_USER_UUID)
            assert data['tenant_uuid'] == str(TOKEN_TENANT_UUID)

        until.assert_(event_received, timeout=5, interval=0.1)

    @fixtures.db.user(uuid=TOKEN_USER_UUID, tenant_uuid=TOKEN_TENANT_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        tenant_uuid=TOKEN_TENANT_UUID,
        backend='test',
        type_='test',
        identity='test:bus-original',
    )
    def test_update_emits_event(self, user, identity):
        accumulator = self.bus.accumulator(
            headers={'name': 'chatd_user_identity_updated'}
        )

        self.chatd.user_identities.update(
            str(TOKEN_USER_UUID),
            str(identity.uuid),
            {'backend': 'test', 'type': 'test', 'identity': 'test:bus-updated'},
        )

        def event_received():
            events = accumulator.accumulate(with_headers=True)
            matching = [
                e
                for e in events
                if e['message']['data'].get('uuid') == str(identity.uuid)
            ]
            assert len(matching) == 1
            data = matching[0]['message']['data']
            assert data['identity'] == 'test:bus-updated'

        until.assert_(event_received, timeout=5, interval=0.1)

    @fixtures.db.user(uuid=TOKEN_USER_UUID, tenant_uuid=TOKEN_TENANT_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        tenant_uuid=TOKEN_TENANT_UUID,
        backend='test',
        type_='test',
        identity='test:bus-deleted',
    )
    def test_delete_emits_event(self, user, identity):
        accumulator = self.bus.accumulator(
            headers={'name': 'chatd_user_identity_deleted'}
        )

        self.chatd.user_identities.delete(str(TOKEN_USER_UUID), str(identity.uuid))

        def event_received():
            events = accumulator.accumulate(with_headers=True)
            matching = [
                e
                for e in events
                if e['message']['data'].get('uuid') == str(identity.uuid)
            ]
            assert len(matching) == 1

        until.assert_(event_received, timeout=5, interval=0.1)
