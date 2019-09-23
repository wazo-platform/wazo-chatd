# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy import and_, text

from ...exceptions import UnknownLineException
from ..helpers import get_dao_session
from ..models import Line


class LineDAO:
    @property
    def session(self):
        return get_dao_session()

    def get(self, line_id):
        line = self._find_by(id=line_id)
        if not line:
            raise UnknownLineException(line_id)
        return line

    def find(self, line_id):
        return self._find_by(id=line_id)

    def _find_by(self, **kwargs):
        filter_ = text('true')

        if 'id' in kwargs:
            filter_ = and_(filter_, Line.id == kwargs['id'])

        return self.session.query(Line).filter(filter_).first()

    def list_(self):
        return self.session.query(Line).all()

    def update(self, line):
        self.session.add(line)
        self.session.flush()

    def associate_endpoint(self, line, endpoint):
        line.endpoint = endpoint
        self.session.flush()

    def dissociate_endpoint(self, line):
        line.endpoint = None
        self.session.flush()
