# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from ...exceptions import UnknownLineException
from ..helpers import get_dao_session
from ..models import Line


class LineDAO:

    @property
    def session(self):
        return get_dao_session()

    def get(self, session_uuid):
        session = self.session.query(Line).get(session_uuid)
        if not session:
            raise UnknownLineException(session_uuid)
        return session

    def list_(self):
        return self.session.query(Line).all()
