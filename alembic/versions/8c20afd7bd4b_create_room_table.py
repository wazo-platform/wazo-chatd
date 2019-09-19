"""create_room_table

Revision ID: 8c20afd7bd4b
Revises: 7b47d171ebf7

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8c20afd7bd4b'
down_revision = '7b47d171ebf7'


def upgrade():
    op.create_table(
        'chatd_room',
        sa.Column(
            'uuid',
            sa.String(36),
            server_default=sa.text('uuid_generate_v4()'),
            primary_key=True,
        ),
        sa.Column('name', sa.Text),
        sa.Column(
            'tenant_uuid',
            sa.String(36),
            sa.ForeignKey('chatd_tenant.uuid', ondelete='CASCADE'),
            nullable=False,
        ),
    )
    op.create_table(
        'chatd_room_user',
        sa.Column(
            'room_uuid',
            sa.String(36),
            sa.ForeignKey('chatd_room.uuid', ondelete='CASCADE'),
            primary_key=True,
        ),
        sa.Column('uuid', sa.String(36), primary_key=True),
        sa.Column('tenant_uuid', sa.String(36), primary_key=True),
        sa.Column('wazo_uuid', sa.String(36), primary_key=True),
    )


def downgrade():
    op.drop_table('chatd_room_user')
    op.drop_table('chatd_room')
