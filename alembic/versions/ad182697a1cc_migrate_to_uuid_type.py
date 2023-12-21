"""migrate-to-uuid-type

Revision ID: ad182697a1cc
Revises: b96789d13584

"""

from contextlib import contextmanager

from sqlalchemy import String
from sqlalchemy_utils import UUIDType

from alembic import op

# revision identifiers, used by Alembic.
revision = 'ad182697a1cc'
down_revision = 'b96789d13584'


def upgrade():
    with disable_user_foreign_key(
        'chatd_refresh_token', 'user_uuid'
    ), disable_user_foreign_key('chatd_session', 'user_uuid'), disable_user_foreign_key(
        'chatd_line', 'user_uuid'
    ):
        convert_column_to_uuid('chatd_user', 'uuid')
        convert_column_to_uuid('chatd_refresh_token', 'user_uuid')
        convert_column_to_uuid('chatd_session', 'user_uuid')
        convert_column_to_uuid('chatd_line', 'user_uuid')

    with disable_tenant_foreign_key(
        'chatd_user', 'tenant_uuid'
    ), disable_tenant_foreign_key('chatd_room', 'tenant_uuid'):
        convert_column_to_uuid('chatd_tenant', 'uuid')
        convert_column_to_uuid('chatd_user', 'tenant_uuid')
        convert_column_to_uuid('chatd_room', 'tenant_uuid')

    with disable_room_foreign_key(
        'chatd_room_user', 'room_uuid'
    ), disable_room_foreign_key('chatd_room_message', 'room_uuid'):
        convert_column_to_uuid('chatd_room', 'uuid')
        convert_column_to_uuid('chatd_room_user', 'room_uuid')
        convert_column_to_uuid('chatd_room_message', 'room_uuid')

    convert_column_to_uuid('chatd_session', 'uuid')
    convert_column_to_uuid('chatd_room_user', 'uuid')
    convert_column_to_uuid('chatd_room_user', 'tenant_uuid')
    convert_column_to_uuid('chatd_room_user', 'wazo_uuid')
    convert_column_to_uuid('chatd_room_message', 'uuid')
    convert_column_to_uuid('chatd_room_message', 'user_uuid')
    convert_column_to_uuid('chatd_room_message', 'tenant_uuid')
    convert_column_to_uuid('chatd_room_message', 'wazo_uuid')


def convert_column_to_uuid(table, column):
    op.alter_column(
        table_name=table,
        column_name=column,
        type_=UUIDType(),
        postgresql_using=f'{column}::uuid',
    )


@contextmanager
def disable_user_foreign_key(table, column):
    with disable_foreign_key(table, 'chatd_user', column, 'uuid'):
        yield


@contextmanager
def disable_tenant_foreign_key(table, column):
    with disable_foreign_key(table, 'chatd_tenant', column, 'uuid'):
        yield


@contextmanager
def disable_room_foreign_key(table, column):
    with disable_foreign_key(table, 'chatd_room', column, 'uuid'):
        yield


@contextmanager
def disable_foreign_key(source_table, referent_table, local_col, remote_col, **kwargs):
    constraint_name = f'{source_table}_{local_col}_fkey'
    op.drop_constraint(constraint_name, source_table)
    yield
    op.create_foreign_key(
        constraint_name,
        source_table,
        referent_table,
        [local_col],
        [remote_col],
        ondelete='CASCADE',
    )


def downgrade():
    with disable_user_foreign_key(
        'chatd_refresh_token', 'user_uuid'
    ), disable_user_foreign_key('chatd_session', 'user_uuid'), disable_user_foreign_key(
        'chatd_line', 'user_uuid'
    ):
        convert_column_to_string('chatd_user', 'uuid')
        convert_column_to_string('chatd_refresh_token', 'user_uuid')
        convert_column_to_string('chatd_session', 'user_uuid')
        convert_column_to_string('chatd_line', 'user_uuid')

    with disable_tenant_foreign_key(
        'chatd_user', 'tenant_uuid'
    ), disable_tenant_foreign_key('chatd_room', 'tenant_uuid'):
        convert_column_to_string('chatd_tenant', 'uuid')
        convert_column_to_string('chatd_user', 'tenant_uuid')
        convert_column_to_string('chatd_room', 'tenant_uuid')

    with disable_room_foreign_key(
        'chatd_room_user', 'room_uuid'
    ), disable_room_foreign_key('chatd_room_message', 'room_uuid'):
        convert_column_to_string('chatd_room', 'uuid')
        convert_column_to_string('chatd_room_user', 'room_uuid')
        convert_column_to_string('chatd_room_message', 'room_uuid')

    convert_column_to_string('chatd_session', 'uuid')
    convert_column_to_string('chatd_room_user', 'uuid')
    convert_column_to_string('chatd_room_user', 'tenant_uuid')
    convert_column_to_string('chatd_room_user', 'wazo_uuid')
    convert_column_to_string('chatd_room_message', 'uuid')
    convert_column_to_string('chatd_room_message', 'user_uuid')
    convert_column_to_string('chatd_room_message', 'tenant_uuid')
    convert_column_to_string('chatd_room_message', 'wazo_uuid')


def convert_column_to_string(table, column):
    op.alter_column(
        table_name=table,
        column_name=column,
        type_=String(36),
    )
