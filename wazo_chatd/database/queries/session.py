# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy.orm import joinedload

from ..helpers import get_dao_session
from ..models import Session


class SessionDAO:

    @property
    def session(self):
        return get_dao_session()

    def get(self, session_uuid):
        return self.session.query(Session).get(session_uuid)

    def list_(self):
        return self.session.query(Session).options(joinedload('user')).all()
