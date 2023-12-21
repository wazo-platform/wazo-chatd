"""add the refresh token table

Revision ID: b96789d13584
Revises: 55c3b35d4b4c

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'b96789d13584'
down_revision = '55c3b35d4b4c'


def upgrade():
    op.create_table(
        'chatd_refresh_token',
        sa.Column('client_id', sa.Text, nullable=False, primary_key=True),
        sa.Column(
            'user_uuid',
            sa.String(36),
            sa.ForeignKey('chatd_user.uuid', ondelete='CASCADE'),
            nullable=False,
            primary_key=True,
        ),
        sa.Column('mobile', sa.Boolean, nullable=False, default=False),
    )


def downgrade():
    op.drop_table('chatd_refresh_token')
