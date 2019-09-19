"""add-away-state-to-presence

Revision ID: fe3c9c8f9b23
Revises: 6c169ed5b4d3

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fe3c9c8f9b23'
down_revision = '6c169ed5b4d3'


def upgrade():
    _update_state_constraint(['available', 'unavailable', 'invisible', 'away'])


def downgrade():
    _update_state_constraint(['available', 'unavailable', 'invisible'])


def _update_state_constraint(new_constraint):
    op.drop_constraint('chatd_user_state_check', 'chatd_user')
    op.create_check_constraint(
        'chatd_user_state_check',
        'chatd_user',
        sa.sql.column('state').in_(new_constraint),
    )
