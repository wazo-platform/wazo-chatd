"""remove_endpoint_states

Revision ID: 543bc8a0045f
Revises: cfbf44983a2b

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '543bc8a0045f'
down_revision = 'cfbf44983a2b'

endpoint_tbl = sa.sql.table('chatd_endpoint')


def upgrade():
    op.execute(endpoint_tbl.delete())
    _update_state_constraint(['available', 'unavailable'])


def downgrade():
    _update_state_constraint(['available', 'unavailable', 'holding', 'ringing', 'talking'])


def _update_state_constraint(new_constraint):
    op.drop_constraint('chatd_endpoint_state_check', 'chatd_endpoint')
    op.create_check_constraint(
        'chatd_endpoint_state_check',
        'chatd_endpoint',
        sa.sql.column('state').in_(new_constraint),
    )
