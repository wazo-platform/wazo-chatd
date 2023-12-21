"""add-progressing-state

Revision ID: 777e588c50f3
Revises: 6ba500c45fcc

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '777e588c50f3'
down_revision = '6ba500c45fcc'


def upgrade():
    _update_channel_state_constraint(
        ['undefined', 'holding', 'ringing', 'talking', 'progressing']
    )


def downgrade():
    _update_channel_state_constraint(['undefined', 'holding', 'ringing', 'talking'])


def _update_channel_state_constraint(new_constraint):
    op.drop_constraint('chatd_channel_state_check', 'chatd_channel')
    op.create_check_constraint(
        'chatd_channel_state_check',
        'chatd_channel',
        sa.sql.column('state').in_(new_constraint),
    )
