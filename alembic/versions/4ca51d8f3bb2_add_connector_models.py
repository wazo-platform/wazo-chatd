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

    # ChatProvider: local cache of confd-managed providers
    op.create_table(
        'chatd_provider',
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
        sa.Column('type', sa.String, nullable=False),
        sa.Column('backend', sa.String, nullable=False),
        sa.Column('name', sa.String, nullable=False),
        sa.Column('description', sa.String, nullable=True),
        sa.Column(
            'configuration',
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_unique_constraint(
        'chatd_provider__uq__tenant_uuid_name',
        'chatd_provider',
        ['tenant_uuid', 'name'],
    )
    op.create_index(
        'chatd_provider__idx__tenant_uuid',
        'chatd_provider',
        ['tenant_uuid'],
    )

    # UserAlias: local cache of confd-managed user aliases
    op.create_table(
        'chatd_user_alias',
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
        sa.Column(
            'provider_uuid',
            UUIDType(),
            sa.ForeignKey('chatd_provider.uuid', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('identity', sa.String, nullable=False),
        sa.Column(
            'extra',
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_unique_constraint(
        'chatd_user_alias__uq__provider_uuid_identity',
        'chatd_user_alias',
        ['provider_uuid', 'identity'],
    )

    # MessageMeta: optional 1:1 delivery metadata for RoomMessage
    op.create_table(
        'chatd_message_meta',
        sa.Column(
            'message_uuid',
            UUIDType(),
            sa.ForeignKey('chatd_room_message.uuid', ondelete='CASCADE'),
            primary_key=True,
        ),
        sa.Column('type', sa.String, nullable=True),
        sa.Column('backend', sa.String, nullable=True),
        sa.Column(
            'identity_uuid',
            UUIDType(),
            sa.ForeignKey('chatd_user_alias.uuid', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('retry_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('external_id', sa.String, nullable=True),
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
    op.create_index(
        'chatd_message_meta__idx__external_id',
        'chatd_message_meta',
        ['external_id'],
    )

    # DeliveryRecord: append-only status updates from connectors
    op.create_table(
        'chatd_delivery_record',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            'message_uuid',
            UUIDType(),
            sa.ForeignKey('chatd_message_meta.message_uuid', ondelete='CASCADE'),
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


def downgrade() -> None:
    op.drop_table('chatd_delivery_record')
    op.drop_table('chatd_message_meta')
    op.drop_table('chatd_user_alias')
    op.drop_index('chatd_provider__idx__tenant_uuid', 'chatd_provider')
    op.drop_table('chatd_provider')
    op.drop_index('chatd_room_user__idx__identity', 'chatd_room_user')
    op.drop_column('chatd_room_user', 'identity')
