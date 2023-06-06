# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import fields
from typing import Any, get_type_hints
from typing_extensions import Self, ClassVar

from .client import CacheClient

_TYPES = (
    'CachedUser',
    'CachedSession',
    'CachedRefrehToken',
    'CachedChannel',
    'CachedEndpoint',
    'CachedLine',
)


def _asdict_inner(obj, toplevel=False):
    if isinstance(obj, BaseModel):
        if not toplevel:
            return obj.pkey()
        result = []
        for f in fields(obj):
            value = _asdict_inner(getattr(obj, f.name))
            result.append((f.name, value))
        return dict(result)
    elif isinstance(obj, tuple) and hasattr(obj, '_fields'):
        return type(obj)(*[_asdict_inner(v) for v in obj])
    elif isinstance(obj, (list, tuple)):
        return type(obj)(_asdict_inner(v) for v in obj)
    elif isinstance(obj, dict):
        return type(obj)((_asdict_inner(k), _asdict_inner(v)) for k, v in obj.items())
    else:
        return deepcopy(obj)


def asdict(obj):
    if not isinstance(obj, BaseModel):
        raise TypeError("asdict() should be called on dataclass instances")
    return _asdict_inner(obj, True)


class BaseModel(ABC):
    _registry: ClassVar[str]
    _prefix: ClassVar[str]
    _pk: ClassVar[str]

    @staticmethod
    def _save_recursively(context: dict, obj: Any) -> dict:
        if isinstance(obj, BaseModel):
            key = obj.pkey()
            if key in context:
                return
            context[key] = asdict(obj)
            for f in fields(obj):
                BaseModel._save_recursively(context, getattr(obj, f.name))
        elif isinstance(obj, (list, tuple, set)):
            [BaseModel._save_recursively(context, v) for v in obj]
        elif isinstance(obj, dict):
            [BaseModel._save_recursively(context, v) for v in obj.values()]
        return context

    def store(self, client: CacheClient):
        models = self._save_recursively({}, self)
        client.save(**models)

    @classmethod
    def restore(cls, client: CacheClient, key: str) -> Self:
        context = {}

        def load(context: dict, obj: Any):
            if isinstance(obj, BaseModel):
                for f in fields(obj):
                    if f.type in _TYPES:
                        key = getattr(obj, f.name)
                        if key not in context:
                            context[key] = eval(f.type)._load(client, key)
                        setattr(obj, f.name, context[key])
                        continue
                    load(context, getattr(obj, f.name))
            elif isinstance(obj, (list, tuple, set)):
                obj = type(obj)(*[load(context, v) for v in obj])
            elif isinstance(obj, dict):
                obj = type(obj)((k, load(context, v)) for k, v in obj.items())
            return obj

        base = cls._load(client, key)
        return load(context, base)

    @classmethod
    def all(cls, client: CacheClient) -> list[Self]:
        # return [cls.unmarshal(client, data) for data in client.load_all(cls._registry)]
        return [cls.restore(client, key) for key in client.array_values(cls._registry)]

    @classmethod
    def exists(cls, client: CacheClient, key: str) -> bool:
        return client.array_find(cls._registry, key)

    @classmethod
    @abstractmethod
    def from_sql(self) -> Self:
        pass

    @classmethod
    def _load(cls, client: CacheClient, key: str) -> Self:
        pkey = str(key)
        if not pkey.startswith(f'{cls._prefix}:'):
            pkey = ':'.join([cls._prefix, pkey])

        if not (data := client.load(pkey)):
            raise ValueError(f'no such {cls._prefix}: {cls._pk}={key}')
        return cls(**data)

    @classmethod
    def load(cls, client: CacheClient, key: str) -> Self:
        pkey = str(key)
        if not pkey.startswith(f'{cls._prefix}:'):
            pkey = ':'.join([cls._prefix, pkey])

        if not (data := client.load(pkey)):
            raise ValueError(f'no such {cls._prefix}: {cls._pk}={key}')
        return cls.unmarshal(client, data)

    @abstractmethod
    def marshal(self) -> dict:
        pass

    def pkey(self) -> str:
        return f'{self._prefix}:{getattr(self, self._pk)}'

    def remove(self, client: CacheClient):
        client.delete(self.pkey())

    def save(self, client: CacheClient):
        client.save(**self.marshal())

    @classmethod
    @abstractmethod
    def unmarshal(cls, client: CacheClient, data: dict) -> Self:
        pass
