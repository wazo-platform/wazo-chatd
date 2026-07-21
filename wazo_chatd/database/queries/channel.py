# Copyright 2020-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from ..helpers import bulk_insert
from ..models import Channel


class ChannelDAO:
    def __init__(self, session):
        self._session = session

    @property
    def session(self):
        return self._session()

    def find(self, name):
        return self._find_by(name=name)

    def _find_by(self, **kwargs):
        query = self.session.query(Channel)

        if 'name' in kwargs:
            query = query.filter(Channel.name == kwargs['name'])

        return query.first()

    def update(self, channel):
        self.session.add(channel)
        self.session.flush()

    def create_all(self, channels: list[Channel]) -> None:
        bulk_insert(self.session, channels)

    def delete_all(self):
        self.session.query(Channel).delete()
        self.session.flush()
