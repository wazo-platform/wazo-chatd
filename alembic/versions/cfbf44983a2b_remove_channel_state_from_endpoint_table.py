"""remove_channel_state_from_endpoint_table

Revision ID: cfbf44983a2b
Revises: 67850df6768f

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'cfbf44983a2b'
down_revision = '67850df6768f'


def upgrade():
    op.drop_column('chatd_endpoint', 'channel_state')


def downgrade():
    op.add_column(
        'chatd_endpoint',
        sa.Column(
            'channel_state',
            sa.String(24),
            sa.CheckConstraint("channel_state in ('up', 'down')"),
        ),
    )
