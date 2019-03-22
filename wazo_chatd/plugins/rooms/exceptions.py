# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo.rest_api_helpers import APIException


class DuplicateUserException(APIException):

    def __init__(self):
        msg = 'Duplicate user detected'
        super().__init__(400, msg, 'duplicate-user', {}, 'rooms')
