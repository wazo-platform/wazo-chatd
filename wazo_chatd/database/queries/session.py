# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy import Boolean
from sqlalchemy.orm import joinedload
from sqlalchemy_utils import UUIDType

from ...exceptions import UnknownSessionException
from ..helpers import bulk_delete, bulk_insert, bulk_update
from ..models import Session


class SessionDAO:
    def __init__(self, session):
        self._session = session

    @property
    def session(self):
        return self._session()

    def get(self, session_uuid):
        session = self._find_by(uuid=session_uuid)
        if not session:
            raise UnknownSessionException(session_uuid)
        return session

    def find(self, session_uuid):
        return self._find_by(uuid=session_uuid)

    def _find_by(self, **kwargs):
        query = self.session.query(Session)

        if 'uuid' in kwargs:
            query = query.filter(Session.uuid == kwargs['uuid'])

        return query.first()

    def list_(self):
        return self.session.query(Session).options(joinedload(Session.user)).all()

    def update(self, session):
        self.session.add(session)
        self.session.flush()

    def create_all(self, sessions):
        bulk_insert(self.session, sessions)

    def delete_by_uuids(self, uuids):
        bulk_delete(self.session, Session, Session.uuid, uuids)

    def update_all(self, sessions):
        bulk_update(
            self.session,
            Session,
            columns=[('uuid', UUIDType()), ('mobile', Boolean)],
            rows=[(session['uuid'], session['mobile']) for session in sessions],
            key_columns=['uuid'],
        )
