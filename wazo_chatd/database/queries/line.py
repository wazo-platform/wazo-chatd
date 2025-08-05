# Copyright 2019-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from ...exceptions import UnknownLineException
from ..models import Line


class LineDAO:
    def __init__(self, session):
        self._session = session

    @property
    def session(self):
        return self._session()

    def get(self, line_id):
        line = self._find_by(id=line_id)
        if not line:
            raise UnknownLineException(line_id)
        return line

    def find(self, line_id):
        return self._find_by(id=line_id)

    def find_by(self, **kwargs):
        return self._find_by(**kwargs)

    def _find_by(self, **kwargs):
        query = self.session.query(Line)

        if 'id' in kwargs:
            query = query.filter(Line.id == kwargs['id'])
        if 'endpoint_name' in kwargs:
            query = query.filter(Line.endpoint_name == kwargs['endpoint_name'])

        return query.first()

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

    def add_channel(self, line, channel):
        if channel not in line.channels:
            line.channels.append(channel)
            self.session.flush()

    def remove_channel(self, line, channel):
        if channel in line.channels:
            line.channels.remove(channel)
            self.session.flush()
