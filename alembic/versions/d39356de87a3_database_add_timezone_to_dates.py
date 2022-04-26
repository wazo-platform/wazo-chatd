"""database: add timezone to dates

Revision ID: d39356de87a3
Revises: 777e588c50f3

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd39356de87a3'
down_revision = '777e588c50f3'


def add_timezone_from_utc(table_name, column_name):
    intermediary_column = column_name + '_without_timezone'
    op.alter_column(
        table_name,
        column_name,
        new_column_name=intermediary_column,
    )
    op.add_column(
        table_name,
        sa.Column(column_name, sa.DateTime(timezone=True)),
    )
    op.execute(
        f"UPDATE {table_name} SET {column_name} = {intermediary_column} at time zone 'utc'"
    )
    op.drop_column(table_name, intermediary_column)


def remove_timezone_at_utc(table_name, column_name):
    intermediary_column = column_name + '_with_timezone'
    op.alter_column(
        table_name,
        column_name,
        new_column_name=intermediary_column,
    )
    op.add_column(
        table_name,
        sa.Column(column_name, sa.DateTime()),
    )
    op.execute(
        f"UPDATE {table_name} SET {column_name} = {intermediary_column} at time zone 'utc'"
    )
    op.drop_column(table_name, intermediary_column)


def upgrade():
    add_timezone_from_utc('chatd_user', 'last_activity')

    add_timezone_from_utc('chatd_room_message', 'created_at')
    op.alter_column(
        'chatd_room_message',
        'created_at',
        nullable=False,
    )


def downgrade():
    remove_timezone_at_utc('chatd_user', 'last_activity')

    remove_timezone_at_utc('chatd_room_message', 'created_at')
    op.alter_column(
        'chatd_room_message',
        'created_at',
        nullable=False,
    )
