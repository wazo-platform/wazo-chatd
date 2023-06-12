# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json

from redis import Redis
from typing import Mapping


class CacheClient:
    def __init__(self, host: str, port: int = 6379):
        self._client = Redis(
            host, port, db=0, decode_responses=True, max_connections=10
        )

    @classmethod
    def from_config(cls, config: dict):
        cache_config = config['cache']
        return cls(**cache_config)

    def load_all(self, array_name: str) -> list[dict | None]:
        keys = self.array_values(array_name)
        if not keys:
            return []
        data = self._client.mget(*keys)
        return [json.loads(obj) for obj in data if obj]

    def load(self, key: str) -> dict:
        if data := self._client.get(key):
            return json.loads(data)
        return None

    def save(self, **mapping: Mapping[str, dict]) -> None:
        data = {key: json.dumps(value) for key, value in mapping.items()}
        self._client.mset(data)

        for pk in data.keys():
            type_ = self._extract_type(pk)
            self.array_insert(type_, pk)

    def delete(self, *keys: str) -> None:
        self._client.delete(*keys)
        for key in keys:
            type_ = self._extract_type(key)
            self.array_remove(type_, key)

    def array_insert(self, array_name: str, obj_name: str):
        if not self._client.sismember(array_name, obj_name):
            self._client.sadd(array_name, obj_name)

    def array_remove(self, array_name: str, obj_name: str):
        self._client.srem(array_name, obj_name)

    def array_find(self, array_name: str, obj_name: str) -> bool:
        return self._client.sismember(array_name, obj_name)

    def array_values(self, array_name: str) -> list:
        return self._client.smembers(array_name)

    def _extract_type(self, pk: str) -> str:
        type_ = pk.split(':', 1)[0]
        if not type_.endswith('s'):
            type_ += 's'
        return type_
