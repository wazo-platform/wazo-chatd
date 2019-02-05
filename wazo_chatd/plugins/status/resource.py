# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo.auth_verifier import required_acl

from wazo_chatd.http import AuthResource


class StatusResource(AuthResource):

    @required_acl('chatd.status.read')
    def get(self):
        result = {
            'rest_api': {
                'status': 'ok',
            }
        }
        return result, 200
