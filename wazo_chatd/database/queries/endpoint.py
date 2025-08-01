# Copyright 2019-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from ...exceptions import UnknownEndpointException
from ..models import Endpoint


class EndpointDAO:
    def __init__(self, session):
        self._session = session

    @property
    def session(self):
        return self._session()

    def create(self, endpoint):
        self.session.add(endpoint)
        self.session.flush()
        return endpoint

    def find_by(self, **kwargs):
        return self._find_by(**kwargs)

    def get_by(self, **kwargs):
        endpoint = self._find_by(**kwargs)
        if not endpoint:
            raise UnknownEndpointException(kwargs.get('name'))
        return endpoint

    def find_or_create(self, name):
        endpoint = self._find_by(name=name)
        if not endpoint:
            endpoint = self.create(Endpoint(name=name))
        return endpoint

    def _find_by(self, **kwargs):
        query = self.session.query(Endpoint)

        if 'name' in kwargs:
            query = query.filter(Endpoint.name == kwargs['name'])

        return query.first()

    def update(self, endpoint):
        self.session.add(endpoint)
        self.session.flush()

    def delete_all(self):
        self.session.query(Endpoint).delete()
        self.session.flush()
