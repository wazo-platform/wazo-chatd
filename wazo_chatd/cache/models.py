# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any, get_args
from typing_extensions import ClassVar, Self

from wazo_chatd.database.models import (
    Channel,
    Endpoint,
    Line,
    RefreshToken,
    Session,
    User,
)

from .client import CacheClient


_TYPES = (
    'CachedUser',
    'CachedSession',
    'CachedRefreshToken',
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
            if f.metadata.get('foreign_key'):
                continue
            value = _asdict_inner(getattr(obj, f.name))
            result.append((f.name, value))
        return dict(result)
    elif isinstance(obj, tuple) and hasattr(obj, '_fields'):
        return type(obj)(*[_asdict_inner(v) for v in obj])
    elif isinstance(obj, (list, tuple)):
        return type(obj)(_asdict_inner(v) for v in obj)
    elif isinstance(obj, dict):
        return type(obj)((_asdict_inner(k), _asdict_inner(v)) for k, v in obj.items())
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return deepcopy(obj)


def asdict(obj):
    if not isinstance(obj, BaseModel):
        raise TypeError("asdict() should be called on dataclass instances")
    return _asdict_inner(obj, True)


class CacheProtocol:
    @classmethod
    def _encode_inner(cls, context: dict, obj: Any) -> dict:
        if isinstance(obj, BaseModel):
            key = obj.pkey()
            if key in context:
                return
            context[key] = asdict(obj)
            for f in fields(obj):
                cls._encode_inner(context, getattr(obj, f.name))
        elif isinstance(obj, (list, tuple, set)):
            [cls._encode_inner(context, v) for v in obj]
        elif isinstance(obj, dict):
            [cls._encode_inner(context, v) for v in obj.values()]
        return context

    @classmethod
    def encode(cls, obj: BaseModel):
        context = {}
        return cls._encode_inner(context, obj)


def relationship(*, key: str = None, many: bool = False):
    kwargs = {
        'init': True,
        'repr': False,
        'compare': False,
        'metadata': {'many': many},
    }

    if many:
        kwargs['default_factory'] = list
    else:
        kwargs['default'] = None

    if key:
        kwargs['metadata']['foreign_key'] = key
    return field(**kwargs)


def load_with_relationship(
    client: CacheClient, context: dict, obj: Any, type_hint: Any
) -> Any:
    type_hint = eval(type_hint) if isinstance(type_hint, str) else type_hint

    if isinstance(obj, BaseModel):
        for f in fields(obj):
            value = getattr(obj, f.name)
            if foreign_field := f.metadata.get('foreign_key'):
                if foreign_key := getattr(obj, foreign_field):
                    value = ':'.join([eval(f.type)._prefix, str(foreign_key)])
            setattr(obj, f.name, load_with_relationship(client, context, value, f.type))
    elif isinstance(obj, (list, set, tuple)):
        item_type = get_args(type_hint)[0]
        return type(obj)(
            load_with_relationship(client, context, value, item_type) for value in obj
        )
    elif obj and type_hint is datetime:
        return datetime.fromisoformat(obj)
    elif isinstance(obj, str) and any(kw in str(type_hint) for kw in _TYPES):
        if not obj.startswith(f'{type_hint._prefix}:'):
            obj = ':'.join([type_hint._prefix, obj])

        if obj in context:
            return context[obj]
        context[obj] = type_hint.load(client, obj)
        return load_with_relationship(client, context, context[obj], type_hint)
    return obj


class BaseModel(ABC):
    _registry: ClassVar[str]
    _prefix: ClassVar[str]
    _pk: ClassVar[str]

    def store(self, client: CacheClient):
        encoded = CacheProtocol.encode(self)
        client.save(**encoded)

    @classmethod
    def restore(cls, client: CacheClient, key: str) -> Self:
        return load_with_relationship(client, {}, str(key), cls)

    @classmethod
    def all(cls, client: CacheClient) -> list[Self]:
        return [cls.restore(client, key) for key in client.array_values(cls._registry)]

    @classmethod
    def exists(cls, client: CacheClient, key: str) -> bool:
        return client.array_find(cls._registry, key)

    @classmethod
    def pk_all(cls, client: CacheClient) -> set[str]:
        return client.array_values(cls._registry)

    @classmethod
    def pk_matches(cls, client: CacheClient, partial_pkey: str) -> set[str]:
        return {
            value
            for value in client.array_values(cls._registry)
            if partial_pkey in value
        }

    @classmethod
    @abstractmethod
    def from_sql(self) -> Self:
        pass

    @classmethod
    def load(cls, client: CacheClient, key: str) -> Self:
        pkey = str(key)
        if not pkey.startswith(f'{cls._prefix}:'):
            pkey = ':'.join([cls._prefix, pkey])

        if not (data := client.load(pkey)):
            raise ValueError(f'no such {cls._prefix}: {cls._pk}={key}')
        return cls(**data)

    def pkey(self) -> str:
        if isinstance(self._pk, (list, tuple)):
            return ':'.join([self._prefix, *(getattr(self, pk) for pk in self._pk)])
        return f'{self._prefix}:{getattr(self, self._pk)}'

    def remove(self, client: CacheClient):
        client.delete(self.pkey())


@dataclass
class CachedUser(BaseModel):
    _registry: ClassVar[str] = 'users'
    _prefix: ClassVar[str] = 'user'
    _pk: ClassVar[str] = 'uuid'

    uuid: str
    tenant_uuid: str
    state: str
    status: str
    do_not_disturb: bool
    last_activity: datetime

    lines: list[CachedLine] = relationship(many=True)
    refresh_tokens: list[CachedRefreshToken] = relationship(many=True)
    sessions: list[CachedSession] = relationship(many=True)

    @classmethod
    def from_sql(cls, user: User):
        sessions = [CachedSession.from_sql(session) for session in user.sessions]
        refresh_tokens = [
            CachedRefreshToken.from_sql(token) for token in user.refresh_tokens
        ]
        lines = [CachedLine.from_sql(line) for line in user.lines]
        return cls(
            str(user.uuid),
            str(user.tenant_uuid),
            user.state,
            user.status,
            user.do_not_disturb,
            user.last_activity,
            lines=lines,
            sessions=sessions,
            refresh_tokens=refresh_tokens,
        )

    def to_sql(self):
        db_user = User()
        db_user.uuid = self.uuid
        db_user.tenant_uuid = self.tenant_uuid
        db_user.state = self.state
        db_user.status = self.status
        return db_user


@dataclass
class CachedLine(BaseModel):
    _registry: ClassVar[str] = 'lines'
    _prefix: ClassVar[str] = 'line'
    _pk: ClassVar[str] = 'id'

    id: int
    user_uuid: str
    endpoint_name: str
    media: str
    tenant_uuid: str

    endpoint: CachedEndpoint = relationship(key='endpoint_name')
    channels: list[CachedChannel] = relationship(many=True)
    user: CachedUser = relationship(key='user_uuid')

    @property
    def endpoint_state(self) -> str:
        try:
            return self.endpoint.state
        except AttributeError:
            return None

    @endpoint_state.setter
    def endpoint_state(self, value: str):
        self.endpoint.state = value

    @property
    def channels_state(self) -> list[str]:
        return [channel.state for channel in self.channels]

    @classmethod
    def from_sql(cls, line: Line):
        endpoint = CachedEndpoint.from_sql(line.endpoint) if line.endpoint else None
        channels = [CachedChannel.from_sql(channel) for channel in line.channels]
        return cls(
            int(line.id),
            str(line.user_uuid),
            line.endpoint_name,
            line.media,
            str(line.tenant_uuid),
            endpoint=endpoint,
            channels=channels,
        )


@dataclass
class CachedSession(BaseModel):
    _registry: ClassVar[str] = 'sessions'
    _prefix: ClassVar[str] = 'session'
    _pk: ClassVar[str] = 'uuid'

    uuid: str
    mobile: bool
    user_uuid: str
    tenant_uuid: str

    user: CachedUser = relationship(key='user_uuid')

    @classmethod
    def from_sql(cls, session: Session):
        return cls(
            str(session.uuid),
            session.mobile,
            str(session.user_uuid),
            str(session.tenant_uuid),
        )


@dataclass
class CachedRefreshToken(BaseModel):
    _registry: ClassVar[str] = 'refresh_tokens'
    _prefix: ClassVar[str] = 'refresh_token'
    _pk: ClassVar[str] = ['user_uuid', 'client_id']

    client_id: str
    user_uuid: str
    mobile: bool
    tenant_uuid: str

    user: CachedUser = relationship(key='user_uuid')

    @classmethod
    def from_sql(cls, refresh_token: RefreshToken):
        return cls(
            str(refresh_token.client_id),
            str(refresh_token.user_uuid),
            refresh_token.mobile,
            str(refresh_token.tenant_uuid),
        )


@dataclass
class CachedChannel(BaseModel):
    _registry: ClassVar[str] = 'channels'
    _prefix: ClassVar[str] = 'channel'
    _pk: ClassVar[str] = 'name'

    name: str
    state: str
    line_id: int

    line: CachedLine = relationship(key='line_id')

    @classmethod
    def from_sql(cls, channel: Channel):
        return cls(channel.name, channel.state, channel.line_id)


@dataclass
class CachedEndpoint(BaseModel):
    _registry: ClassVar[str] = 'endpoints'
    _prefix: ClassVar[str] = 'endpoint'
    _pk: ClassVar[str] = 'name'

    name: str
    state: str
    line_id: int = field(default=None)

    line: CachedLine = relationship(key='line_id')

    @classmethod
    def from_sql(cls, endpoint: Endpoint):
        return cls(endpoint.name, endpoint.state)
