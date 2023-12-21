"""create_user_table

Revision ID: f5083f715fb9
Revises: None

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'f5083f715fb9'
down_revision = None


def upgrade():
    op.create_table('chatd_tenant', sa.Column('uuid', sa.String(36), primary_key=True))
    op.create_table(
        'chatd_user',
        sa.Column('uuid', sa.String(36), primary_key=True),
        sa.Column(
            'tenant_uuid',
            sa.String(36),
            sa.ForeignKey('chatd_tenant.uuid', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'state',
            sa.String(24),
            sa.CheckConstraint("state in ('available', 'unavailable', 'invisible')"),
            nullable=False,
        ),
        sa.Column('status', sa.Text),
    )


def downgrade():
    op.drop_table('chatd_user')
    op.drop_table('chatd_tenant')
