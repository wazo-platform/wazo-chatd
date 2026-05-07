# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid

from sqlalchemy import select
from wazo_test_helpers import until

from wazo_chatd.database.models import (
    DeliveryRecord,
    MessageDelivery,
    MessageMeta,
    RoomMessage,
)

from .helpers import fixtures
from .helpers.base import (
    TOKEN_TENANT_UUID,
    TOKEN_USER_UUID,
    ConnectorIntegrationTest,
    use_asset,
)

USER_UUID_1 = uuid.uuid4()
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

        response = self.post_webhook(
            json={
                'from': EXTERNAL_IDENTITY,
                'to': 'test:+15551234',
                'body': 'Hello from outside',
                'message_id': 'ext-msg-001',
            },
        )

        assert response.status_code == 204

        def message_persisted():
            message = self._session.execute(
                select(RoomMessage).where(RoomMessage.content == 'Hello from outside')
            ).scalar_one_or_none()
            assert message is not None

            meta = self._session.execute(
                select(MessageMeta).where(MessageMeta.message_uuid == message.uuid)
            ).scalar_one_or_none()
            assert meta is not None
            assert meta.backend == 'test'
            assert meta.type_ == 'test'

        until.assert_(message_persisted, timeout=5, interval=0.1)

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='test',
        identity='test:+15551234',
    )
    def test_webhook_with_backend_hint(self, user, identity):

        response = self.post_webhook(
            backend='test',
            json={
                'from': EXTERNAL_IDENTITY,
                'to': 'test:+15551234',
                'body': 'Hello with hint',
                'message_id': 'ext-msg-002',
            },
        )

        assert response.status_code == 204

        def message_persisted():
            message = self._session.execute(
                select(RoomMessage).where(RoomMessage.content == 'Hello with hint')
            ).scalar_one_or_none()
            assert message is not None

        until.assert_(message_persisted, timeout=5, interval=0.1)

    def test_webhook_unrecognized_payload_returns_400(self):
        response = self.post_webhook(
            json={'body': 'hello'},
            headers={
                'X-Test-Connector': 'true',
                'Content-Type': 'application/json',
            },
        )

        assert response.status_code == 400
        assert response.json().get('error_id') == 'webhook-parse-error'
        self._assert_no_message_with_body('hello')

    def test_webhook_unknown_recipient_returns_400(self):
        response = self.post_webhook(
            json={
                'from': EXTERNAL_IDENTITY,
                'to': 'test:+15559999',
                'body': 'unrouted',
                'message_id': 'ext-no-tenant',
            },
        )

        assert response.status_code == 400
        assert response.json().get('error_id') == 'webhook-parse-error'
        self._assert_no_message_with_body('unrouted')

    def _assert_no_message_with_body(self, body: str) -> None:
        messages = list(
            self._session.execute(
                select(RoomMessage).where(RoomMessage.content == body)
            ).scalars()
        )
        assert messages == []

    @fixtures.db.user(uuid=USER_UUID_1)
    def test_webhook_drops_after_last_identity_deleted(self, user):
        identity = self.chatd.user_identities.create(
            str(USER_UUID_1),
            {'backend': 'test', 'type': 'test', 'identity': 'test:+15559950'},
        )

        response = self.post_webhook(
            json={
                'from': EXTERNAL_IDENTITY,
                'to': 'test:+15559950',
                'body': 'before delete',
                'message_id': 'ext-drop-1',
            },
        )
        assert response.status_code == 204

        self.chatd.user_identities.delete(str(USER_UUID_1), identity['uuid'])

        response = self.post_webhook(
            json={
                'from': EXTERNAL_IDENTITY,
                'to': 'test:+15559950',
                'body': 'after delete',
                'message_id': 'ext-drop-2',
            },
        )
        assert response.status_code == 400
        assert response.json().get('error_id') == 'webhook-parse-error'

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='test',
        identity='test:+15551234',
    )
    def test_webhook_accepts_form_encoded_body(self, user, identity):
        response = self.post_webhook(
            data={
                'from': EXTERNAL_IDENTITY,
                'to': 'test:+15551234',
                'body': 'form-encoded inbound',
                'message_id': 'ext-form-1',
            },
        )

        assert response.status_code == 204

        def message_persisted():
            messages = list(
                self._session.execute(
                    select(RoomMessage).where(
                        RoomMessage.content == 'form-encoded inbound'
                    )
                ).scalars()
            )
            assert len(messages) == 1

        until.assert_(message_persisted, timeout=5, interval=0.1)

    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.db.user_identity(
        user_uuid=USER_UUID_1,
        backend='test',
        identity='test:+15551234',
    )
    def test_webhook_duplicate_idempotency_skipped(self, user, identity):
        first = {
            'from': EXTERNAL_IDENTITY,
            'to': 'test:+15551234',
            'body': 'Dedup test',
            'message_id': 'ext-msg-dedup-1',
            'idempotency_key': 'unique-key-001',
        }
        second = {
            'from': EXTERNAL_IDENTITY,
            'to': 'test:+15551234',
            'body': 'Dedup test',
            'message_id': 'ext-msg-dedup-2',
            'idempotency_key': 'unique-key-001',
        }

        assert self.post_webhook(json=first).status_code == 204

        def first_message_persisted():
            messages = list(
                self._session.execute(
                    select(RoomMessage).where(RoomMessage.content == 'Dedup test')
                ).scalars()
            )
            assert len(messages) == 1

        until.assert_(first_message_persisted, timeout=5, interval=0.1)

        assert self.post_webhook(json=second).status_code == 204

        def still_one_message():
            messages = list(
                self._session.execute(
                    select(RoomMessage).where(RoomMessage.content == 'Dedup test')
                ).scalars()
            )
            assert len(messages) == 1

        until.assert_(still_one_message, timeout=3, interval=0.1)


@use_asset('connectors')
class TestOutboundDelivery(ConnectorIntegrationTest):
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

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'Hello external', 'sender_identity_uuid': str(identity.uuid)},
        )

        self.assert_delivery_status(message['uuid'], 'accepted')

        meta = self._session.execute(
            select(MessageMeta).where(MessageMeta.message_uuid == message['uuid'])
        ).scalar_one_or_none()
        assert meta is not None
        assert meta.backend == 'test'
        assert meta.type_ == 'test'

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
            assert len(sent) == 1
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
    def test_failed_delivery_creates_retrying_record(self, user, identity, room):

        self.connector_mock.set_config(send_behavior='fail', error_message='API down')

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'Will fail', 'sender_identity_uuid': str(identity.uuid)},
        )

        self.assert_delivery_status(message['uuid'], 'retrying')

        delivery = self._session.execute(
            select(MessageDelivery).where(
                MessageDelivery.message_uuid == message['uuid']
            )
        ).scalar_one()
        assert delivery.retry_count == 1
        assert delivery.external_id is None


@use_asset('connectors')
class TestStatusUpdate(ConnectorIntegrationTest):
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

        self.connector_mock.set_config(
            send_behavior='succeed', external_id='ext-status-001'
        )

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'Track this', 'sender_identity_uuid': str(identity.uuid)},
        )

        self.assert_delivery_status(message['uuid'], 'accepted')

        response = self.post_webhook(
            json={'external_id': 'ext-status-001', 'status': 'delivered'},
        )
        assert response.status_code == 204

        self.assert_delivery_status(message['uuid'], 'delivered')

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

        self.assert_delivery_status(message['uuid'], 'accepted')

        response = self.post_webhook(
            json={
                'external_id': 'ext-status-002',
                'status': 'failed',
                'error_code': '30003',
            },
        )
        assert response.status_code == 204

        def has_failed_with_reason():
            failed = [
                r
                for r in self.get_delivery_records(message['uuid'])
                if r.status == 'failed'
            ]
            assert len(failed) == 1
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

        self.connector_mock.set_config(
            send_behavior='succeed', external_id='ext-status-003'
        )

        message = self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'Transient status', 'sender_identity_uuid': str(identity.uuid)},
        )

        self.assert_delivery_status(message['uuid'], 'accepted')

        response = self.post_webhook(
            json={'external_id': 'ext-status-003', 'status': 'queued'},
        )
        assert response.status_code == 204

        def transient_ignored_but_pipeline_ran():
            statuses = [r.status for r in self.get_delivery_records(message['uuid'])]
            assert 'accepted' in statuses
            assert 'queued' not in statuses

        until.assert_(transient_ignored_but_pipeline_ran, timeout=3, interval=0.1)


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

        self.connector_mock.set_config(
            send_behavior='succeed', external_id='ext-outbound-001'
        )

        room_uuid = room['uuid']

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

        response = self.post_webhook(
            json={
                'from': 'test:+15559876',
                'to': 'test:+15551234',
                'body': 'SMS reply from user B',
                'message_id': 'ext-msg-multichannel',
            },
        )
        assert response.status_code == 204

        def all_messages_in_same_room():
            messages = list(
                self._session.execute(
                    select(RoomMessage).where(RoomMessage.room_uuid == room_uuid)
                ).scalars()
            )
            contents = [m.content for m in messages]
            assert 'Internal hello' in contents
            assert 'Sending by SMS' in contents
            assert 'SMS reply from user B' in contents

        until.assert_(all_messages_in_same_room, timeout=5, interval=0.1)

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
    def test_inbound_echo_of_outbound_is_dropped(
        self, user_a, user_b, identity_a, identity_b, room
    ):
        self.connector_mock.set_config(
            send_behavior='succeed', external_id='ext-echo-001'
        )

        room_uuid = room['uuid']

        self.chatd.rooms.create_message_from_user(
            room_uuid,
            {
                'content': 'Echo test message',
                'sender_identity_uuid': str(identity_a.uuid),
            },
        )

        def outbound_sent():
            sent = self.connector_mock.get_sent_messages()
            assert any(m['body'] == 'Echo test message' for m in sent)

        until.assert_(outbound_sent, timeout=5, interval=0.1)

        response = self.post_webhook(
            json={
                'from': 'test:+15551234',
                'to': 'test:+15559876',
                'body': 'Echo test message',
                'message_id': 'ext-echo-inbound',
            },
        )
        assert response.status_code == 204

        def echo_acknowledged_on_outbound():
            stmt = (
                select(DeliveryRecord)
                .join(
                    MessageDelivery,
                    MessageDelivery.id == DeliveryRecord.delivery_id,
                )
                .where(MessageDelivery.external_id == 'ext-echo-001')
                .where(DeliveryRecord.status == 'delivered')
            )
            records = list(self._session.execute(stmt).scalars())
            assert records, 'echo not acknowledged on outbound delivery yet'

        until.assert_(echo_acknowledged_on_outbound, timeout=5, interval=0.1)

        def still_one_message():
            messages = list(
                self._session.execute(
                    select(RoomMessage).where(RoomMessage.room_uuid == room_uuid)
                ).scalars()
            )
            echo_messages = [m for m in messages if m.content == 'Echo test message']
            assert len(echo_messages) == 1

        until.assert_(still_one_message, timeout=3, interval=0.1)


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
        assert message['delivery']['type'] == 'internal'
        assert message['delivery']['backend'] is None
        assert message['delivery']['recipients'] == []

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
    def test_connector_message_has_type_from_identity(self, user, identity, room):
        self.chatd.rooms.create_message_from_user(
            str(room.uuid),
            {'content': 'Typed message', 'sender_identity_uuid': str(identity.uuid)},
        )

        def message_has_type():
            messages = self.chatd.rooms.list_messages_from_user(str(room.uuid))
            connector_msgs = [
                m for m in messages['items'] if m['content'] == 'Typed message'
            ]
            assert len(connector_msgs) == 1
            assert connector_msgs[0]['delivery']['type'] == 'test'
            assert connector_msgs[0]['delivery']['backend'] == 'test'

        until.assert_(message_has_type, timeout=5, interval=0.1)


@use_asset('connectors')
class TestMessageVisibility(ConnectorIntegrationTest):
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
    def test_sender_sees_own_pending_message(
        self, user_a, user_b, identity_a, identity_b, room
    ):
        self.connector_mock.set_config(
            send_behavior='succeed', external_id='ext-vis-001'
        )

        self.chatd.rooms.create_message_from_user(
            room['uuid'],
            {
                'content': 'Visible to sender',
                'sender_identity_uuid': str(identity_a.uuid),
            },
        )

        messages = self.chatd.rooms.list_messages_from_user(room['uuid'])
        contents = [m['content'] for m in messages['items']]
        assert 'Visible to sender' in contents

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
    def test_other_user_does_not_see_pending_message(
        self, user_a, user_b, identity_a, identity_b, room
    ):
        self.connector_mock.set_config(
            send_behavior='succeed', external_id='ext-vis-002'
        )

        message = self.chatd.rooms.create_message_from_user(
            room['uuid'],
            {
                'content': 'Not yet visible',
                'sender_identity_uuid': str(identity_a.uuid),
            },
        )

        self.assert_delivery_status(message['uuid'], 'accepted')

        chatd_b = self.make_user_chatd(USER_UUID_1, TOKEN_TENANT_UUID)
        messages = chatd_b.rooms.list_messages_from_user(room['uuid'])
        assert messages['total'] == 0
        assert messages['items'] == []

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
    def test_other_user_sees_message_after_delivery(
        self, user_a, user_b, identity_a, identity_b, room
    ):
        self.connector_mock.set_config(
            send_behavior='succeed', external_id='ext-vis-003'
        )

        self.chatd.rooms.create_message_from_user(
            room['uuid'],
            {
                'content': 'Will be delivered',
                'sender_identity_uuid': str(identity_a.uuid),
            },
        )

        def accepted():
            stmt = (
                select(DeliveryRecord)
                .join(MessageDelivery, MessageDelivery.id == DeliveryRecord.delivery_id)
                .join(
                    MessageMeta,
                    MessageMeta.message_uuid == MessageDelivery.message_uuid,
                )
                .join(RoomMessage, RoomMessage.uuid == MessageMeta.message_uuid)
                .where(RoomMessage.content == 'Will be delivered')
            )
            records = list(self._session.execute(stmt).scalars())
            statuses = [r.status for r in records]
            assert 'accepted' in statuses

        until.assert_(accepted, timeout=5, interval=0.1)

        self.post_webhook(
            json={'external_id': 'ext-vis-003', 'status': 'delivered'},
        )

        chatd_b = self.make_user_chatd(USER_UUID_1, TOKEN_TENANT_UUID)

        def visible_to_b():
            messages = chatd_b.rooms.list_messages_from_user(room['uuid'])
            contents = [m['content'] for m in messages['items']]
            assert 'Will be delivered' in contents

        until.assert_(visible_to_b, timeout=5, interval=0.1)

    @fixtures.db.user(uuid=TOKEN_USER_UUID)
    @fixtures.db.user(uuid=USER_UUID_1)
    @fixtures.http.room(
        users=[
            {'uuid': str(TOKEN_USER_UUID)},
            {'uuid': str(USER_UUID_1)},
        ],
    )
    def test_internal_message_visible_to_all(self, user_a, user_b, room):
        self.chatd.rooms.create_message_from_user(
            room['uuid'], {'content': 'Internal hello'}
        )

        chatd_b = self.make_user_chatd(USER_UUID_1, TOKEN_TENANT_UUID)
        messages = chatd_b.rooms.list_messages_from_user(room['uuid'])
        contents = [m['content'] for m in messages['items']]
        assert 'Internal hello' in contents
