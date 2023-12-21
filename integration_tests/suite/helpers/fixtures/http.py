# Copyright 2019-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid
from functools import wraps

from wazo_chatd.database.models import Room

from ..base import TOKEN_USER_UUID


def room(**room_args):
    def decorator(decorated):
        @wraps(decorated)
        def wrapper(self, *args, **kwargs):
            room_args.setdefault('users', [])
            if not room_args['users']:
                room_args['users'].append({'uuid': str(uuid.uuid4())})
            elif len(room_args['users']) == 1 and room_args['users'][0]['uuid'] == str(
                TOKEN_USER_UUID
            ):
                room_args['users'].append({'uuid': str(uuid.uuid4())})

            room = self.chatd.rooms.create_from_user(room_args)

            args = list(args) + [room]
            try:
                result = decorated(self, *args, **kwargs)
            finally:
                self._session.expunge_all()
                self._session.query(Room).filter(Room.uuid == room['uuid']).delete()
                self._session.commit()
            return result

        return wrapper

    return decorator
