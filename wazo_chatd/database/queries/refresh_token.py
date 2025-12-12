# Copyright 2019-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy.orm import joinedload

from ...exceptions import UnknownRefreshTokenException
from ..models import RefreshToken


class RefreshTokenDAO:
    def __init__(self, session):
        self._session = session

    @property
    def session(self):
        return self._session()

    def get(self, user_uuid, client_id):
        refresh_token = self.session.get(RefreshToken, (client_id, user_uuid))
        if not refresh_token:
            raise UnknownRefreshTokenException(client_id, user_uuid)
        return refresh_token

    def find(self, user_uuid, client_id):
        return self._find_by(user_uuid=user_uuid, client_id=client_id)

    def _find_by(self, **kwargs):
        query = self.session.query(RefreshToken)

        if 'user_uuid' in kwargs:
            query = query.filter(RefreshToken.user_uuid == kwargs['user_uuid'])
        if 'client_id' in kwargs:
            query = query.filter(RefreshToken.client_id == kwargs['client_id'])

        return query.first()

    def list_(self):
        return (
            self.session.query(RefreshToken)
            .options(joinedload(RefreshToken.user))
            .all()
        )

    def update(self, refresh_token):
        self.session.add(refresh_token)
        self.session.flush()
