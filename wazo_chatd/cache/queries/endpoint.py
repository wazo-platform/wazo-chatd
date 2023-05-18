# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from wazo_chatd.cache import get_local_cache, get_endpoint_cache
from wazo_chatd.cache.models import CachedEndpoint
from wazo_chatd.database.models import Endpoint
from wazo_chatd.exceptions import UnknownEndpointException

logger = logging.getLogger(__name__)


class EndpointCache:
    @property
    def cache(self):
        return get_endpoint_cache()

    @property
    def endpoints(self):
        return get_endpoint_cache().values()

    @property
    def lines(self):
        users = get_local_cache().values()
        return [line for user in users for line in user.lines]

    def create(self, endpoint: Endpoint):
        cached = self.cache[endpoint.name] = CachedEndpoint.from_sql(endpoint)
        return self.from_cache(cached)

    def find_by(self, **kwargs):
        endpoints = self.endpoints
        name = kwargs.pop('name', None)
        if name:
            endpoints = [endpoint for endpoint in endpoints if endpoint.name == name]

        if endpoints:
            return self.from_cache(endpoints[0])
        return None

    def get_by(self, **kwargs):
        endpoint = self.find_by(**kwargs)
        if endpoint:
            return self.from_cache(endpoint)
        raise UnknownEndpointException(kwargs['name'])

    def find_or_create(self, name: str):
        endpoint = self.find_by(name=name)
        if endpoint:
            return self.from_cache(endpoint)
        return self.create(Endpoint(name=name))

    def update(self, endpoint: Endpoint):
        cached = CachedEndpoint.from_sql(endpoint)
        for existing_endpoint in self.endpoints:
            if existing_endpoint.name == endpoint.name:
                existing_endpoint = cached
        else:
            get_endpoint_cache()[endpoint.name] = cached

    def delete_all(self):
        for line in self.lines:
            line.endpoint = None
            line.endpoint_name = None
        self.cache.clear()

    @staticmethod
    def from_cache(endpoint: CachedEndpoint):
        users = get_local_cache().values()

        endpoint.line = None
        for user in users:
            for line in user.lines:
                if line.endpoint_name == endpoint.name:
                    endpoint.line = line
                    endpoint.line.user = user
                    break
        return endpoint
