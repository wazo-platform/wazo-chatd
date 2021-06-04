"""add-progressing-state

Revision ID: 777e588c50f3
Revises: 6ba500c45fcc

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '777e588c50f3'
down_revision = '6ba500c45fcc'


def upgrade():
    _update_line_state_constraint(['available', 'unavailable', 'holding', 'ringing', 'talking', 'progressing'])


def downgrade():
    _update_line_state_constraint(['available', 'unavailable', 'holding', 'ringing', 'talking'])


def _update_line_state_constraint(new_constraint):
    op.drop_constraint('chatd_line_state_check', 'chatd_line')
    op.create_check_constraint(
        'chatd_line_state_check',
        'chatd_line',
        sa.sql.column('state').in_(new_constraint),
    )
