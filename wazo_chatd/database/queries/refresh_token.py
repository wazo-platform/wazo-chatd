# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy.orm import joinedload

from ...exceptions import UnknownRefreshTokenException
from ..helpers import get_dao_session
from ..models import RefreshToken


class RefreshTokenDAO:
    @property
    def session(self):
        return get_dao_session()

    def get(self, user_uuid, client_id):
        refresh_token = self.session.query(RefreshToken).get((client_id, user_uuid))
        if not refresh_token:
            raise UnknownRefreshTokenException(client_id, user_uuid)
        return refresh_token

    def list_(self):
        return self.session.query(RefreshToken).options(joinedload('user')).all()
