# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

import requests
from wazo_test_helpers import until

from .helpers import fixtures
from .helpers.base import TOKEN_USER_UUID, ConnectorIntegrationTest, use_asset

EXTERNAL_IDENTITY = 'test:+15559876'
SENDER_IDENTITY = 'test:+15551234'
RECIPIENT_UUID = uuid.uuid4()
USER_UUID_RECIPIENT = uuid.uuid4()


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

        port = self.asset_cls.service_port(9304, 'chatd')
        response = requests.post(
            f'http://127.0.0.1:{port}/1.0/connectors/incoming',
            json={
                'from': EXTERNAL_IDENTITY,
                'to': SENDER_IDENTITY,
                'body': 'Inbound event test',
                'message_id': f'ext-bus-{uuid.uuid4()}',
            },
            headers={'X-Test-Connector': 'true'},
        )
        assert response.status_code == 204

        recipient_header = f'user_uuid:{TOKEN_USER_UUID}'

        def event_received():
            events = accumulator.accumulate(with_headers=True)
            assert len(events) >= 1
            data = events[0]['message']['data']
            assert data['content'] == 'Inbound event test'
            delivery = data['delivery']
            assert delivery['type'] == 'test'
            assert delivery['backend'] == 'test'

        until.assert_(event_received, timeout=5, interval=0.1)

        events = accumulator.accumulate(with_headers=True)
        inbound_events = [
            e
            for e in events
            if e['message']['data'].get('content') == 'Inbound event test'
        ]
        user_uuid_headers = sorted(
            h
            for e in inbound_events
            for h in e['headers']
            if h.startswith('user_uuid:') and e['headers'][h] is True
        )
        assert user_uuid_headers == [recipient_header], (
            f'expected exactly one event for recipient {TOKEN_USER_UUID}, got '
            f'user_uuid headers: {user_uuid_headers}'
        )


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

        port = self.asset_cls.service_port(9304, 'chatd')
        requests.post(
            f'http://127.0.0.1:{port}/1.0/connectors/incoming',
            json={
                'external_id': 'ext-bus-status-001',
                'status': 'delivered',
            },
            headers={'X-Test-Connector': 'true'},
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
class TestEchoConfirmationNotifiesRecipient(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user(uuid=USER_UUID_RECIPIENT)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity=SENDER_IDENTITY,
    )
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_RECIPIENT,
        backend='test',
        identity=EXTERNAL_IDENTITY,
    )
    @fixtures.http.room(
        users=[
            {'uuid': str(TOKEN_USER_UUID)},
            {'uuid': str(USER_UUID_RECIPIENT)},
        ],
    )
    def test_echo_path_publishes_room_message_created_for_recipient(
        self, user_a, user_b, identity_a, identity_b, room
    ):
        accumulator = self.bus.accumulator(
            headers={'name': 'chatd_user_room_message_created'}
        )

        self.connector_mock.reset()
        self.connector_mock.set_config(
            send_behavior='succeed', external_id='ext-echo-event-001'
        )

        room_uuid = room['uuid']
        port = self.asset_cls.service_port(9304, 'chatd')

        self.chatd.rooms.create_message_from_user(
            room_uuid,
            {
                'content': 'echo notify test',
                'sender_identity_uuid': str(identity_a.uuid),
            },
        )

        def outbound_sent():
            sent = self.connector_mock.get_sent_messages()
            assert any(m['body'] == 'echo notify test' for m in sent)

        until.assert_(outbound_sent, timeout=5, interval=0.1)

        response = requests.post(
            f'http://127.0.0.1:{port}/1.0/connectors/incoming',
            json={
                'from': SENDER_IDENTITY,
                'to': EXTERNAL_IDENTITY,
                'body': 'echo notify test',
                'message_id': 'ext-echo-notify-001',
            },
            headers={'X-Test-Connector': 'true'},
        )
        assert response.status_code == 204

        sender_header = f'user_uuid:{TOKEN_USER_UUID}'
        recipient_header = f'user_uuid:{USER_UUID_RECIPIENT}'

        def recipient_received_event():
            events = accumulator.accumulate(with_headers=True)
            matching = [
                e
                for e in events
                if e['message']['data'].get('content') == 'echo notify test'
            ]
            recipient_events = [
                e for e in matching if e['headers'].get(recipient_header) is True
            ]
            assert len(recipient_events) >= 1, (
                f'recipient {USER_UUID_RECIPIENT} got no '
                f'chatd_user_room_message_created (echo path); '
                f'matching headers: {[e["headers"] for e in matching]}'
            )

        until.assert_(recipient_received_event, timeout=5, interval=0.1)

        events = accumulator.accumulate(with_headers=True)
        echo_matches = [
            e
            for e in events
            if e['message']['data'].get('content') == 'echo notify test'
        ]
        recipients = [
            h
            for e in echo_matches
            for h in e['headers']
            if h.startswith('user_uuid:') and e['headers'][h] is True
        ]
        assert (
            recipients.count(sender_header) == 1
        ), f'sender event count != 1: {recipients}'
        assert (
            recipients.count(recipient_header) == 1
        ), f'recipient event count != 1: {recipients}'
        assert set(recipients) == {
            sender_header,
            recipient_header,
        }, f'unexpected user_uuid header in echo events: {recipients}'

        recipient_event = next(
            e for e in echo_matches if e['headers'].get(recipient_header) is True
        )
        recipient_data_user_uuid = recipient_event['message']['data'].get('user_uuid')
        assert recipient_data_user_uuid == str(TOKEN_USER_UUID), (
            'data.user_uuid must be the message sender so webhookd does not '
            f'suppress the push to recipient {USER_UUID_RECIPIENT}; '
            f'got {recipient_data_user_uuid}'
        )
