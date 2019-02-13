# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from ...exceptions import UnknownLineException
from ..helpers import get_dao_session
from ..models import Line


class LineDAO:

    @property
    def session(self):
        return get_dao_session()

    def get(self, line_id):
        session = self.session.query(Line).get(line_id)
        if not session:
            raise UnknownLineException(line_id)
        return session

    def list_(self):
        return self.session.query(Line).all()

    def update(self, line):
        self.session.add(line)
        self.session.flush()
