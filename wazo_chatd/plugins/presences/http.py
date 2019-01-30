# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo.auth_verifier import required_acl

from wazo_chatd.http import AuthResource


class PresenceListResource(AuthResource):

    @required_acl('chatd.users.presences.read')
    def get(self):
        return {}, 200
