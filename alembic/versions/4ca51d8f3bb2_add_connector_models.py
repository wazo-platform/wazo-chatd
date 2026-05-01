# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""add connector models

Revision ID: 4ca51d8f3bb2
Revises: e700870ac284

"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy_utils import UUIDType

from alembic import op

# revision identifiers, used by Alembic.
revision = '4ca51d8f3bb2'
down_revision = 'e700870ac284'


def upgrade() -> None:
    # RoomUser: add identity column for external participants
    op.add_column(
        'chatd_room_user',
        sa.Column('identity', sa.String, nullable=True),
    )
    op.create_index(
        'chatd_room_user__idx__identity',
        'chatd_room_user',
        ['identity'],
    )

    # UserIdentity: user-to-external-identity mappings
    op.create_table(
        'chatd_user_identity',
        sa.Column(
            'uuid',
            UUIDType(),
            server_default=sa.text('uuid_generate_v4()'),
            primary_key=True,
        ),
        sa.Column(
            'tenant_uuid',
            UUIDType(),
            sa.ForeignKey('chatd_tenant.uuid', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'user_uuid',
            UUIDType(),
            sa.ForeignKey('chatd_user.uuid', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('backend', sa.String, nullable=False),
        sa.Column('type', sa.String, nullable=False),
        sa.Column('identity', sa.String, nullable=False),
        sa.Column(
            'extra',
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_unique_constraint(
        'chatd_user_identity__uq__backend_identity_type',
        'chatd_user_identity',
        ['backend', 'identity', 'type'],
    )
    op.create_index(
        'chatd_user_identity__idx__tenant_uuid',
        'chatd_user_identity',
        ['tenant_uuid'],
    )
    op.create_index(
        'chatd_user_identity__idx__user_uuid',
        'chatd_user_identity',
        ['user_uuid'],
    )

    # MessageMeta: per-message metadata (sender, opaque extras)
    op.create_table(
        'chatd_message_meta',
        sa.Column(
            'message_uuid',
            UUIDType(),
            sa.ForeignKey('chatd_room_message.uuid', ondelete='CASCADE'),
            primary_key=True,
        ),
        sa.Column(
            'sender_identity_uuid',
            UUIDType(),
            sa.ForeignKey('chatd_user_identity.uuid', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'extra',
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        'chatd_message_meta__idx__extra',
        'chatd_message_meta',
        ['extra'],
        postgresql_using='gin',
    )

    # MessageDelivery: per-recipient delivery state (1 row per leg)
    op.create_table(
        'chatd_message_delivery',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            'message_uuid',
            UUIDType(),
            sa.ForeignKey('chatd_message_meta.message_uuid', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('recipient_identity', sa.String, nullable=False),
        sa.Column('backend', sa.String, nullable=False),
        sa.Column('type', sa.String, nullable=False),
        sa.Column('external_id', sa.String, nullable=True),
        sa.Column('retry_count', sa.SmallInteger, nullable=False, server_default='0'),
        sa.UniqueConstraint(
            'message_uuid',
            'recipient_identity',
            name='chatd_message_delivery__uq__msg_recipient',
        ),
    )
    op.create_index(
        'chatd_message_delivery__uq__external_id',
        'chatd_message_delivery',
        ['external_id', 'backend'],
        unique=True,
        postgresql_where='external_id IS NOT NULL',
    )

    # DeliveryRecord: append-only status timeline per delivery
    op.create_table(
        'chatd_delivery_record',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            'delivery_id',
            sa.Integer,
            sa.ForeignKey('chatd_message_delivery.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('status', sa.String, nullable=False),
        sa.Column('reason', sa.String, nullable=True),
        sa.Column(
            'timestamp',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("(now() at time zone 'utc')"),
        ),
    )
    op.create_index(
        'chatd_delivery_record__idx__delivery_id',
        'chatd_delivery_record',
        ['delivery_id'],
    )


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS chatd_delivery_record CASCADE')
    op.execute('DROP TABLE IF EXISTS chatd_message_delivery CASCADE')
    op.execute('DROP TABLE IF EXISTS chatd_message_meta CASCADE')
    op.execute('DROP TABLE IF EXISTS chatd_user_identity CASCADE')
    op.drop_index('chatd_room_user__idx__identity', 'chatd_room_user')
    op.drop_column('chatd_room_user', 'identity')
