"""create_device_table

Revision ID: 7b47d171ebf7
Revises: c861b92d73d2

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '7b47d171ebf7'
down_revision = 'c861b92d73d2'

line_table = sa.sql.table('chatd_line')


def upgrade():
    op.execute(line_table.delete())
    op.create_table(
        'chatd_device',
        sa.Column('name', sa.Text, primary_key=True),
        sa.Column(
            'state',
            sa.String(24),
            sa.CheckConstraint("state in ('available', 'unavailable', 'holding', 'ringing', 'talking')"),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        'chatd_line_device_name_fkey',
        'chatd_line', 'chatd_device',
        ['device_name'], ['name'],
        ondelete='SET NULL',
    )
    op.drop_column('chatd_line', 'state')


def downgrade():
    op.drop_constraint('chatd_line_device_name_fkey', 'chatd_line', type_='foreignkey')
    op.drop_table('chatd_device')
    op.add_column(
        'chatd_line',
        sa.Column(
            'state',
            sa.String(24),
            sa.CheckConstraint("state in ('available', 'unavailable', 'holding', 'ringing', 'talking')"),
            nullable=False,
        ),
    )
