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
        return self.get_by(id=line_id)

    def get_by(self, **kwargs):
        filter_ = text('true')

        if 'id' in kwargs:
            filter_ = and_(filter_, Line.id == kwargs['id'])
        if 'device_name' in kwargs:
            filter_ = and_(filter_, Line.device_name == kwargs['device_name'])

        line = self.session.query(Line).filter(filter_).first()
        if not line:
            raise UnknownLineException(kwargs.get('id'))
        return line

    def list_(self):
        return self.session.query(Line).all()

    def update(self, line):
        self.session.add(line)
        self.session.flush()

    def associate_device(self, line, device):
        line.device = device
        self.session.flush()

    def dissociate_device(self, line, device):
        line.device = None
        self.session.flush()
