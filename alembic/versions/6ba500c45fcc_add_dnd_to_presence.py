"""add dnd to presence

Revision ID: 6ba500c45fcc
Revises: 543bc8a0045f

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '6ba500c45fcc'
down_revision = '543bc8a0045f'

def upgrade():
    op.add_column(
        'chatd_user', sa.Column('do_not_disturb', sa.Boolean, nullable=False, server_default='0')
    )


def downgrade():
    op.drop_column('chatd_user', 'do_not_disturb')
