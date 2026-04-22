# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid
from functools import wraps

from wazo_chatd.database.models import Room, UserIdentity

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

            args = (*args, room)
            try:
                result = decorated(self, *args, **kwargs)
            finally:
                self._session.expunge_all()
                self._session.query(Room).filter(Room.uuid == room['uuid']).delete()
                self._session.commit()
            return result

        return wrapper

    return decorator


def user_identity(**identity_args):
    def decorator(decorated):
        @wraps(decorated)
        def wrapper(self, *args, **kwargs):
            user_uuid = identity_args.pop('user_uuid', TOKEN_USER_UUID)
            identity_args.setdefault('backend', 'test')
            identity_args.setdefault('type', 'test')

            identity = self.chatd.user_identities.create(
                str(user_uuid), identity_args
            )

            args = (*args, identity)
            try:
                result = decorated(self, *args, **kwargs)
            finally:
                self._session.expunge_all()
                self._session.query(UserIdentity).filter(
                    UserIdentity.uuid == identity['uuid']
                ).delete()
                self._session.commit()
            return result

        return wrapper

    return decorator
