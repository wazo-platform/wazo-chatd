# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from wazo_chatd.cache.client import CacheClient
from wazo_chatd.cache.models import CachedEndpoint, CachedLine
from wazo_chatd.database.models import Endpoint as SQLEndpoint
from wazo_chatd.exceptions import UnknownEndpointException

logger = logging.getLogger(__name__)


class EndpointCache:
    def __init__(self, client: CacheClient):
        self._cache = client

    def create(self, endpoint: SQLEndpoint):
        cached_endpoint = CachedEndpoint.from_sql(endpoint)
        cached_endpoint.save(self._cache)
        return cached_endpoint

    def find_by(self, **kwargs):
        if name := kwargs.pop('name', None):
            try:
                return CachedEndpoint.load(self._cache, name)
            except ValueError:
                pass
        return None

    def get_by(self, **kwargs):
        if endpoint := self.find_by(**kwargs):
            return endpoint
        raise UnknownEndpointException(kwargs['name'])

    def find_or_create(self, name: str):
        if endpoint := self.find_by(name=name):
            return endpoint
        return self.create(SQLEndpoint(name=name))

    def update(self, endpoint: CachedEndpoint):
        endpoint.save(self._cache)

    def delete_all(self):
        for line in CachedLine.load_all(self._cache):
            if line.endpoint:
                line.endpoint.delete(self._cache)
                line.endpoint = None
                line.endpoint_name = None
                line.save(self._cache)
