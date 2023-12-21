"""create_channel_table

Revision ID: 67850df6768f
Revises: ad182697a1cc

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '67850df6768f'
down_revision = 'ad182697a1cc'


def upgrade():
    op.create_table(
        'chatd_channel',
        sa.Column('name', sa.Text, primary_key=True),
        sa.Column(
            'state',
            sa.String(24),
            sa.CheckConstraint(
                "state in ('undefined', 'holding', 'ringing', 'talking')"
            ),
            nullable=False,
            default='undefined',
        ),
        sa.Column(
            'line_id',
            sa.Integer,
            sa.ForeignKey('chatd_line.id', ondelete='CASCADE'),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_table('chatd_channel')
