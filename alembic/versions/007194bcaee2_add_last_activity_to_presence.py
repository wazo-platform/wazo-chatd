"""add_last_activity_to_presence

Revision ID: 007194bcaee2
Revises: 6c169ed5b4d3

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007194bcaee2'
down_revision = '6c169ed5b4d3'


def upgrade():
    op.add_column('chatd_user', sa.Column('last_activity', sa.DateTime))


def downgrade():
    op.drop_column('chatd_user', 'last_activity')
