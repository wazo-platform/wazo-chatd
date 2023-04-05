"""add indices for foreign keys

Revision ID: e700870ac284
Revises: c73e58cf659b

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e700870ac284'
down_revision = 'c73e58cf659b'


def upgrade():
    op.create_index('chatd_user__idx__tenant_uuid', 'chatd_user', ['tenant_uuid'])
    op.create_index('chatd_session__idx__user_uuid', 'chatd_session', ['user_uuid'])
    op.create_index('chatd_line__idx__user_uuid', 'chatd_line', ['user_uuid'])
    op.create_index('chatd_line__idx__endpoint_name', 'chatd_line', ['endpoint_name'])
    op.create_index('chatd_channel__idx__line_id', 'chatd_channel', ['line_id'])
    op.create_index('chatd_room__idx__tenant_uuid', 'chatd_room', ['tenant_uuid'])
    op.create_index(
        'chatd_room_message__idx__room_uuid', 'chatd_room_message', ['room_uuid']
    )


def downgrade():
    op.drop_index('chatd_room_message__idx__room_uuid')
    op.drop_index('chatd_room__idx__tenant_uuid')
    op.drop_index('chatd_channel__idx__line_id')
    op.drop_index('chatd_line__idx__endpoint_name')
    op.drop_index('chatd_line__idx__user_uuid')
    op.drop_index('chatd_session__idx__user_uuid')
    op.drop_index('chatd_user__idx__tenant_uuid')
