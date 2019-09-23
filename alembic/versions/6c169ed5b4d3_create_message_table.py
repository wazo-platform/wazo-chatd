"""create_message_table

Revision ID: 6c169ed5b4d3
Revises: 8c20afd7bd4b

"""

import datetime
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '6c169ed5b4d3'
down_revision = '8c20afd7bd4b'


def upgrade():
    op.create_table(
        'chatd_room_message',
        sa.Column(
            'uuid',
            sa.String(36),
            server_default=sa.text('uuid_generate_v4()'),
            primary_key=True,
        ),
        sa.Column(
            'room_uuid',
            sa.String(36),
            sa.ForeignKey('chatd_room.uuid', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('content', sa.Text),
        sa.Column('alias', sa.String(256)),
        sa.Column('user_uuid', sa.String(36), nullable=False),
        sa.Column('tenant_uuid', sa.String(36), nullable=False),
        sa.Column('wazo_uuid', sa.String(36), nullable=False),
        sa.Column(
            'created_at', sa.DateTime, default=datetime.datetime.utcnow, nullable=False
        ),
    )


def downgrade():
    op.drop_table('chatd_room_message')
