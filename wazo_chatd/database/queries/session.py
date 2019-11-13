# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy import and_, text
from sqlalchemy.orm import joinedload

from ...exceptions import UnknownSessionException
from ..helpers import get_dao_session
from ..models import Session


class SessionDAO:
    @property
    def session(self):
        return get_dao_session()

    def get(self, session_uuid):
        session = self._find_by(uuid=session_uuid)
        if not session:
            raise UnknownSessionException(session_uuid)
        return session

    def find(self, session_uuid):
        return self._find_by(uuid=session_uuid)

    def _find_by(self, **kwargs):
        filter_ = text('true')

        if 'uuid' in kwargs:
            filter_ = and_(filter_, Session.uuid == kwargs['uuid'])

        return self.session.query(Session).filter(filter_).first()

    def list_(self):
        return self.session.query(Session).options(joinedload('user')).all()

    def update(self, session):
        self.session.add(session)
        self.session.flush()
