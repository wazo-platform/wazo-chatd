# Copyright 2020 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy import and_, text

from ..helpers import get_dao_session
from ..models import Channel


class ChannelDAO:
    @property
    def session(self):
        return get_dao_session()

    def find(self, name):
        return self._find_by(name=name)

    def _find_by(self, **kwargs):
        filter_ = text('true')

        if 'name' in kwargs:
            filter_ = and_(filter_, Channel.name == kwargs['name'])

        return self.session.query(Channel).filter(filter_).first()

    def update(self, channel):
        self.session.add(channel)
        self.session.flush()

    def delete_all(self):
        self.session.query(Channel).delete()
        self.session.flush()
