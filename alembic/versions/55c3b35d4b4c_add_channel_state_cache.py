"""add_channel_state_cache

Revision ID: 55c3b35d4b4c
Revises: 007194bcaee2

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '55c3b35d4b4c'
down_revision = '007194bcaee2'


def upgrade():
    op.add_column(
        'chatd_endpoint',
        sa.Column(
            'channel_state',
            sa.String(24),
            sa.CheckConstraint("channel_state in ('up', 'down')"),
        ),
    )


def downgrade():
    op.drop_column('chatd_endpoint', 'channel_state')
