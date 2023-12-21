"""add_last_activity_to_presence

Revision ID: 007194bcaee2
Revises: fe3c9c8f9b23

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '007194bcaee2'
down_revision = 'fe3c9c8f9b23'


def upgrade():
    op.add_column('chatd_user', sa.Column('last_activity', sa.DateTime))


def downgrade():
    op.drop_column('chatd_user', 'last_activity')
