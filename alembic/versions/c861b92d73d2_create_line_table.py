"""create_line_table

Revision ID: c861b92d73d2
Revises: f2492ea1fa9e

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'c861b92d73d2'
down_revision = 'f2492ea1fa9e'


def upgrade():
    op.create_table(
        'chatd_line',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column(
            'user_uuid',
            sa.String(36),
            sa.ForeignKey('chatd_user.uuid', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('device_name', sa.Text),
        sa.Column(
            'state',
            sa.String(24),
            sa.CheckConstraint(
                "state in ('available', 'unavailable', 'holding', 'ringing', 'talking')"
            ),
            nullable=False,
        ),
        sa.Column(
            'media', sa.String(24), sa.CheckConstraint("media in ('audio', 'video')")
        ),
    )


def downgrade():
    op.drop_table('chatd_line')
