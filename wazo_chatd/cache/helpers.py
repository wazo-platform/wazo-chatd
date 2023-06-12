# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from abc import abstractmethod
from copy import deepcopy
from dataclasses import Field, field, fields, is_dataclass
from datetime import datetime
from logging import getLogger
from typing import Any, get_args, ClassVar, Iterable, Mapping, Optional, Protocol
from typing_extensions import Self

from .client import CacheClient


logger = getLogger(__name__)


class CacheProtocol(Protocol):
    _registry: ClassVar[str]
    _prefix: ClassVar[str]
    _pk: ClassVar[str | Iterable[str]]

    def delete(self, client: CacheClient) -> None:
        ...

    @classmethod
    @abstractmethod
    def from_sql(cls) -> Self:
        ...

    @classmethod
    def load(cls, client: CacheClient, pk: str) -> Self:
        ...

    @classmethod
    def load_all(cls, client: CacheClient) -> list[Self]:
        ...

    def pk(self) -> str:
        ...

    @classmethod
    def pk_all(cls, client: CacheClient) -> set[str]:
        ...

    @classmethod
    def pk_matches(cls, client: CacheClient, partial_pk: str) -> set[str]:
        ...

    def save(self, client: CacheClient) -> None:
        ...


def _is_model(context: dict, obj: Any) -> bool:
    classes = tuple(context['namespace'].values())
    if isinstance(obj, type):
        return issubclass(obj, classes)
    return isinstance(obj, classes)


def _get_type(context: dict, type_: str) -> Any:
    if not isinstance(type_, str):
        return type_
    return eval(type_, globals(), context['namespace'])


def _is_relationship_field(context: dict, obj: Any, type_hint: Any) -> bool:
    return isinstance(obj, str) and _is_model(context, type_hint)


def _make_pk(object_type: Any, object_key: str) -> str:
    if object_key.startswith(f'{object_type._prefix}:'):
        return object_key
    return ':'.join([object_type._prefix, str(object_key)])


def _load_object(
    client: CacheClient, object_type: CacheProtocol, object_key: str
) -> CacheProtocol:
    pk = _make_pk(object_type, object_key)

    if not (data := client.load(pk)):
        return None
    return object_type(**data)


def load_with_relationship(
    client: CacheClient, context: dict, obj: Any, type_hint: Any
) -> Any:
    type_hint = _get_type(context, type_hint)

    # convert and load referenced model
    if _is_relationship_field(context, obj, type_hint):
        pk = _make_pk(type_hint, obj)
        if pk not in context:
            context[pk] = _load_object(client, type_hint, pk)
            return load_with_relationship(client, context, context[pk], type_hint)
        return context[pk]

    # recurse into model fields
    elif _is_model(context, obj):
        for f in fields(obj):
            value = getattr(obj, f.name)
            if foreign_key := f.metadata.get('foreign_key'):
                if foreign_value := getattr(obj, foreign_key):
                    value = _make_pk(_get_type(context, f.type), str(foreign_value))
            setattr(obj, f.name, load_with_relationship(client, context, value, f.type))

    # recurse into iterable
    elif isinstance(obj, (list, set, tuple)):
        item_type = get_args(type_hint)[0]
        return type(obj)(
            load_with_relationship(client, context, value, item_type) for value in obj
        )

    # convert datetime
    elif obj and type_hint is datetime:
        return datetime.fromisoformat(obj)

    return obj


def relationship_field(
    *, foreign_key: str = None, many: bool = False, cascade_delete: bool = False
) -> Field:
    metadata = {'many': many, 'cascade_delete': cascade_delete}
    kwargs = {'init': True, 'repr': False, 'compare': False, 'metadata': metadata}

    if many:
        kwargs['default_factory'] = list
    else:
        kwargs['default'] = None

    if foreign_key and not many:
        metadata['foreign_key'] = foreign_key
    return field(**kwargs)


def _encode_object(obj: Any, toplevel: bool = False):
    if is_dataclass(obj) and hasattr(obj, 'pk'):
        if not toplevel:
            return obj.pk()

        result = []
        for f in fields(obj):
            if f.metadata.get('foreign_key'):
                continue  # skip, we'll use foreign_key to retrieve later
            value = _encode_object(getattr(obj, f.name))
            result.append((f.name, value))
        return dict(result)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, tuple) and hasattr(obj, '_fields'):
        return type(obj)(*[_encode_object(member) for member in obj])
    elif isinstance(obj, (list, set, tuple)):
        return type(obj)(_encode_object(member) for member in obj)
    elif isinstance(obj, dict):
        return type(obj)((_encode_object(k), _encode_object(v)) for k, v in obj.items())
    else:
        return deepcopy(obj)


def _find_objects(obj: Any, *, mapping: Optional[dict] = None) -> dict:
    mapping = mapping or {}

    if is_dataclass(obj) and hasattr(obj, 'pk'):
        key = obj.pk()
        if key in mapping:
            return mapping
        mapping[key] = obj
        for f in fields(obj):
            _find_objects(getattr(obj, f.name), mapping=mapping)
    elif isinstance(obj, (list, tuple, set)):
        for member in obj:
            _find_objects(member, mapping=mapping)
    elif isinstance(obj, dict):
        for member in obj.values():
            _find_objects(member, mapping=mapping)

    return mapping


def generate_update_mapping(model: CacheProtocol) -> Mapping:
    mapping = _find_objects(model)
    return {pk: _encode_object(value, True) for pk, value in mapping.items()}
