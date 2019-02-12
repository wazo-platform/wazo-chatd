"""create_session_table

Revision ID: f2492ea1fa9e
Revises: f5083f715fb9

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f2492ea1fa9e'
down_revision = 'f5083f715fb9'


def upgrade():
    op.create_table(
        'chatd_session',
        sa.Column('uuid', sa.String(36), primary_key=True),
        sa.Column('mobile', sa.Boolean, nullable=False, default=False),
        sa.Column(
            'user_uuid',
            sa.String(36),
            sa.ForeignKey('chatd_user.uuid', ondelete='CASCADE'),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_table('chatd_session')
