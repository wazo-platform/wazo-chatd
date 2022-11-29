# Copyright 2019-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo.rest_api_helpers import APIException


class DuplicateUserException(APIException):
    def __init__(self):
        msg = 'Duplicate user detected'
        super().__init__(400, msg, 'duplicate-user', {}, 'rooms')


class RoomAlreadyExists(APIException):
    def __init__(self, uuid, users):
        msg = f'Room "{uuid}" already exists for users: "{users}"'
        details = {'uuid': str(uuid), 'users': users}
        super().__init__(409, msg, 'conflict', details, 'rooms')
