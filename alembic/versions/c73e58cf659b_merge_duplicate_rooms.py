"""merge-duplicate-rooms

Revision ID: c73e58cf659b
Revises: d39356de87a3

"""

import sqlalchemy as sa
from sqlalchemy import sql

from alembic import op

# revision identifiers, used by Alembic.
revision = 'c73e58cf659b'
down_revision = 'd39356de87a3'

room_tbl = sql.table(
    'chatd_room',
    sql.column('uuid'),
)

room_message_tbl = sql.table(
    'chatd_room_message',
    sql.column('room_uuid'),
)


def upgrade():
    subquery = sa.text(
        'SELECT room_uuid, array_agg(uuid ORDER BY uuid) AS users FROM chatd_room_user GROUP BY room_uuid'
    )
    query = sa.text(
        f'SELECT array_agg(room_uuid) AS rooms FROM ({subquery}) AS room GROUP BY users HAVING count(*) > 1;'
    )
    results = op.get_bind().execute(query)
    for result in results:
        primary_room_uuid = None
        for room_uuid in result.rooms:
            if primary_room_uuid is None:
                primary_room_uuid = room_uuid
                continue

            query = (
                room_message_tbl.update()
                .where(room_message_tbl.c.room_uuid == room_uuid)
                .values(room_uuid=primary_room_uuid)
            )
            op.execute(query)

            query = room_tbl.delete().where(room_tbl.c.uuid == room_uuid)
            op.execute(query)


def downgrade():
    pass
