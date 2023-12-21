"""create_endpoint_table

Revision ID: 7b47d171ebf7
Revises: c861b92d73d2

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '7b47d171ebf7'
down_revision = 'c861b92d73d2'

line_table = sa.sql.table('chatd_line')


def upgrade():
    op.execute(line_table.delete())
    op.create_table(
        'chatd_endpoint',
        sa.Column('name', sa.Text, primary_key=True),
        sa.Column(
            'state',
            sa.String(24),
            sa.CheckConstraint(
                "state in ('available', 'unavailable', 'holding', 'ringing', 'talking')"
            ),
            nullable=False,
        ),
    )
    op.drop_column('chatd_line', 'state')
    op.drop_column('chatd_line', 'device_name')
    op.add_column(
        'chatd_line',
        sa.Column(
            'endpoint_name',
            sa.Text,
            sa.ForeignKey('chatd_endpoint.name', ondelete='SET NULL'),
        ),
    )


def downgrade():
    op.drop_constraint(
        'chatd_line_endpoint_name_fkey', 'chatd_line', type_='foreignkey'
    )
    op.drop_table('chatd_endpoint')
    op.add_column(
        'chatd_line',
        sa.Column(
            'state',
            sa.String(24),
            sa.CheckConstraint(
                "state in ('available', 'unavailable', 'holding', 'ringing', 'talking')"
            ),
            nullable=False,
        ),
    )
    op.add_column('chatd_line', sa.Column('device_name', sa.Text))
