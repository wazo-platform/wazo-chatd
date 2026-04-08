# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

import requests
from wazo_test_helpers import until

from wazo_chatd.database.models import (
    DeliveryRecord,
    MessageMeta,
    RoomMessage,
)

from .helpers import fixtures
from .helpers.base import TOKEN_USER_UUID, ConnectorIntegrationTest, use_asset

USER_UUID_1 = uuid.uuid4()
USER_UUID_2 = uuid.uuid4()
EXTERNAL_IDENTITY = 'test:+15559876'


@use_asset('connectors')
class TestInboundWebhook(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='test',
        identity='test:+15551234',
    )
    def test_webhook_creates_message_with_meta(self, user, identity):


        webhook_data = {
            'from': EXTERNAL_IDENTITY,
            'to': 'test:+15551234',
            'body': 'Hello from outside',
            'message_id': 'ext-msg-001',
        }

        port = self.asset_cls.service_port(9304, 'chatd')
        response = requests.post(
            f'http://127.0.0.1:{port}/1.0/connectors/incoming',
            json=webhook_data,
            headers={'X-Test-Connector': 'true'},
        )

        assert response.status_code == 204

        def message_persisted():
            message = (
                self._session.query(RoomMessage)
                .filter(RoomMessage.content == 'Hello from outside')
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

        until.assert_(message_persisted, timeout=5, interval=0.1)

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='test',
        identity='test:+15551234',
    )
    def test_webhook_with_backend_hint(self, user, identity):


        webhook_data = {
            'from': EXTERNAL_IDENTITY,
            'to': 'test:+15551234',
            'body': 'Hello with hint',
            'message_id': 'ext-msg-002',
        }

        port = self.asset_cls.service_port(9304, 'chatd')
        response = requests.post(
            f'http://127.0.0.1:{port}/1.0/connectors/incoming/test',
            json=webhook_data,
            headers={'X-Test-Connector': 'true'},
        )

        assert response.status_code == 204

        def message_persisted():
            message = (
                self._session.query(RoomMessage)
                .filter(RoomMessage.content == 'Hello with hint')
                .first()
            )
            assert message is not None

        until.assert_(message_persisted, timeout=5, interval=0.1)

    def test_webhook_unknown_connector_returns_404(self):
        port = self.asset_cls.service_port(9304, 'chatd')
        response = requests.post(
            f'http://127.0.0.1:{port}/1.0/connectors/incoming',
            json={'body': 'hello'},
            headers={'Content-Type': 'application/json'},
        )

        assert response.status_code == 404

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='test',
        identity='test:+15551234',
    )
    def test_webhook_duplicate_idempotency_skipped(self, user, identity):


        webhook_data = {
            'from': EXTERNAL_IDENTITY,
            'to': 'test:+15551234',
            'body': 'Dedup test',
            'message_id': 'ext-msg-dedup',
            'idempotency_key': 'unique-key-001',
        }

        port = self.asset_cls.service_port(9304, 'chatd')

        response = requests.post(
            f'http://127.0.0.1:{port}/1.0/connectors/incoming',
            json=webhook_data,
            headers={'X-Test-Connector': 'true'},
        )
        assert response.status_code == 204

        def first_message_persisted():
            messages = (
                self._session.query(RoomMessage)
                .filter(RoomMessage.content == 'Dedup test')
                .all()
            )
            assert len(messages) == 1

        until.assert_(first_message_persisted, timeout=5, interval=0.1)

        response = requests.post(
            f'http://127.0.0.1:{port}/1.0/connectors/incoming',
            json=webhook_data,
            headers={'X-Test-Connector': 'true'},
        )
        assert response.status_code == 204

        def still_one_message():
            messages = (
                self._session.query(RoomMessage)
                .filter(RoomMessage.content == 'Dedup test')
                .all()
            )
            assert len(messages) == 1

        until.assert_(still_one_message, timeout=3, interval=0.1)


@use_asset('connectors')
class TestOutboundDelivery(ConnectorIntegrationTest):
    def _assert_delivery_status(self, message_uuid: str, expected_status: str) -> None:
        def check():
            records = (
                self._session.query(DeliveryRecord)
                .filter(DeliveryRecord.message_uuid == message_uuid)
                .order_by(DeliveryRecord.timestamp)
                .all()
            )
            statuses = [r.status for r in records]
            assert expected_status in statuses

        until.assert_(check, timeout=5, interval=0.1)

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity='test:+15551234',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_message_in_external_room_creates_delivery_records(
        self, user, identity, room
    ):

        self.connector_mock.reset()

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'Hello external', 'sender_identity_uuid': str(identity.uuid)},
        )

        self._assert_delivery_status(message['uuid'], 'sent')

        meta = (
            self._session.query(MessageMeta)
            .filter(MessageMeta.message_uuid == message['uuid'])
            .first()
        )
        assert meta is not None
        assert meta.backend == 'test'

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity='test:+15551234',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_connector_mock_receives_sent_message(self, user, identity, room):

        self.connector_mock.reset()
        self.connector_mock.set_config(
            send_behavior='succeed',
            external_id='mock-ext-123',
        )

        self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'Check the mock', 'sender_identity_uuid': str(identity.uuid)},
        )

        def mock_received():
            sent = self.connector_mock.get_sent_messages()
            assert len(sent) >= 1
            assert sent[0]['body'] == 'Check the mock'

        until.assert_(mock_received, timeout=5, interval=0.1)

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity='test:+15551234',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_failed_delivery_creates_failed_record(self, user, identity, room):

        self.connector_mock.reset()
        self.connector_mock.set_config(send_behavior='fail', error_message='API down')

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'Will fail', 'sender_identity_uuid': str(identity.uuid)},
        )

        self._assert_delivery_status(message['uuid'], 'failed')


@use_asset('connectors')
class TestStatusUpdate(ConnectorIntegrationTest):
    def _assert_delivery_status(self, message_uuid: str, expected_status: str) -> None:
        def check():
            records = (
                self._session.query(DeliveryRecord)
                .filter(DeliveryRecord.message_uuid == message_uuid)
                .order_by(DeliveryRecord.timestamp)
                .all()
            )
            statuses = [r.status for r in records]
            assert expected_status in statuses

        until.assert_(check, timeout=5, interval=0.1)

    def _get_external_id(self, message_uuid: str) -> str:
        def check():
            meta = (
                self._session.query(MessageMeta)
                .filter(MessageMeta.message_uuid == message_uuid)
                .first()
            )
            assert meta is not None
            assert meta.external_id is not None
            return meta.external_id

        return until.return_(check, timeout=5, interval=0.1)

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity='test:+15551234',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_delivered_status_creates_record(self, user, identity, room):

        self.connector_mock.reset()
        self.connector_mock.set_config(
            send_behavior='succeed', external_id='ext-status-001'
        )

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'Track this', 'sender_identity_uuid': str(identity.uuid)},
        )

        self._assert_delivery_status(message['uuid'], 'sent')

        port = self.asset_cls.service_port(9304, 'chatd')
        response = requests.post(
            f'http://127.0.0.1:{port}/1.0/connectors/incoming',
            json={
                'external_id': 'ext-status-001',
                'status': 'delivered',
            },
            headers={'X-Test-Connector': 'true'},
        )
        assert response.status_code == 204

        self._assert_delivery_status(message['uuid'], 'delivered')

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity='test:+15551234',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_failed_status_creates_record_with_reason(self, user, identity, room):

        self.connector_mock.reset()
        self.connector_mock.set_config(
            send_behavior='succeed', external_id='ext-status-002'
        )

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {
                'content': 'Will get failed status',
                'sender_identity_uuid': str(identity.uuid),
            },
        )

        self._assert_delivery_status(message['uuid'], 'sent')

        port = self.asset_cls.service_port(9304, 'chatd')
        response = requests.post(
            f'http://127.0.0.1:{port}/1.0/connectors/incoming',
            json={
                'external_id': 'ext-status-002',
                'status': 'failed',
                'error_code': '30003',
            },
            headers={'X-Test-Connector': 'true'},
        )
        assert response.status_code == 204

        def has_failed_with_reason():
            records = (
                self._session.query(DeliveryRecord)
                .filter(DeliveryRecord.message_uuid == message['uuid'])
                .order_by(DeliveryRecord.timestamp)
                .all()
            )
            failed = [r for r in records if r.status == 'failed']
            assert len(failed) >= 1
            assert failed[0].reason == '30003'

        until.assert_(has_failed_with_reason, timeout=5, interval=0.1)

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity='test:+15551234',
    )
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4(), 'identity': EXTERNAL_IDENTITY},
        ],
    )
    def test_transient_status_is_ignored(self, user, identity, room):

        self.connector_mock.reset()
        self.connector_mock.set_config(
            send_behavior='succeed', external_id='ext-status-003'
        )

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'Transient status', 'sender_identity_uuid': str(identity.uuid)},
        )

        self._assert_delivery_status(message['uuid'], 'sent')

        port = self.asset_cls.service_port(9304, 'chatd')
        response = requests.post(
            f'http://127.0.0.1:{port}/1.0/connectors/incoming',
            json={
                'external_id': 'ext-status-003',
                'status': 'queued',
            },
            headers={'X-Test-Connector': 'true'},
        )
        assert response.status_code == 204

        def no_queued_record():
            records = (
                self._session.query(DeliveryRecord)
                .filter(DeliveryRecord.message_uuid == message['uuid'])
                .order_by(DeliveryRecord.timestamp)
                .all()
            )
            statuses = [r.status for r in records]
            assert 'queued' not in statuses

        until.assert_(no_queued_record, timeout=3, interval=0.1)


@use_asset('connectors')
class TestMultiChannelRoom(ConnectorIntegrationTest):
    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=TOKEN_USER_UUID,
        backend='test',
        identity='test:+15551234',
    )
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='test',
        identity='test:+15559876',
    )
    @fixtures.http.room(
        users=[
            {'uuid': str(TOKEN_USER_UUID)},
            {'uuid': str(USER_UUID_1)},
        ],
    )
    def test_full_multichannel_flow(self, user_a, user_b, identity_a, identity_b, room):

        self.connector_mock.reset()
        self.connector_mock.set_config(
            send_behavior='succeed', external_id='ext-outbound-001'
        )

        room_uuid = room['uuid']
        port = self.asset_cls.service_port(9304, 'chatd')

        self.chatd.rooms.create_message_from_user(
            room_uuid, {'content': 'Internal hello'}
        )

        self.chatd.rooms.create_message_from_user(
            room_uuid,
            {'content': 'Sending by SMS', 'sender_identity_uuid': str(identity_a.uuid)},
        )

        def mock_received_outbound():
            sent = self.connector_mock.get_sent_messages()
            assert any(m['body'] == 'Sending by SMS' for m in sent)

        until.assert_(mock_received_outbound, timeout=5, interval=0.1)

        response = requests.post(
            f'http://127.0.0.1:{port}/1.0/connectors/incoming',
            json={
                'from': 'test:+15559876',
                'to': 'test:+15551234',
                'body': 'SMS reply from user B',
                'message_id': 'ext-msg-multichannel',
            },
            headers={'X-Test-Connector': 'true'},
        )
        assert response.status_code == 204

        def all_messages_in_same_room():
            messages = (
                self._session.query(RoomMessage)
                .filter(RoomMessage.room_uuid == room_uuid)
                .all()
            )
            contents = [m.content for m in messages]
            assert 'Internal hello' in contents
            assert 'Sending by SMS' in contents
            assert 'SMS reply from user B' in contents

        until.assert_(all_messages_in_same_room, timeout=5, interval=0.1)


@use_asset('connectors')
class TestMessageSchemaFields(ConnectorIntegrationTest):
    @fixtures.db.room(
        users=[
            {'uuid': TOKEN_USER_UUID},
            {'uuid': uuid.uuid4()},
        ],
        messages=[{'content': 'internal message', 'user_uuid': TOKEN_USER_UUID}],
    )
    def test_internal_message_has_type_internal(self, room):
        messages = self.chatd.rooms.list_messages_from_user(str(room.uuid))

        message = messages['items'][0]
        assert message['type'] == 'internal'
        assert message['backend'] is None
