# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypeVar
from typing_extensions import ClassVar, Self

from wazo_chatd.cache.client import CacheClient
from wazo_chatd.cache.helpers import (
    CacheProtocol,
    generate_update_mapping,
    load_with_relationship,
    relationship_field,
)
from wazo_chatd.database.models import (
    Channel as SQLChannel,
    Endpoint as SQLEndpoint,
    Line as SQLLine,
    RefreshToken as SQLRefreshToken,
    Session as SQLSession,
    User as SQLUser,
)


SQLModel = TypeVar(
    'SQLModel', SQLChannel, SQLEndpoint, SQLLine, SQLRefreshToken, SQLSession, SQLUser
)


class BaseModel(ABC, CacheProtocol):
    @staticmethod
    def __build_context():
        namespace = {cls.__name__: cls for cls in BaseModel.__subclasses__()}
        return {'namespace': namespace}

    def delete(self, client: CacheClient) -> None:
        client.delete(*[self.pk()])

    @classmethod
    @abstractmethod
    def from_sql(cls, obj: SQLModel) -> Self:
        pass

    @classmethod
    def load(cls, client: CacheClient, pk: str) -> Self:
        context = cls.__build_context()
        if not (obj := load_with_relationship(client, context, str(pk), cls)):
            raise ValueError(f'no such {cls._prefix} in cache: \"{pk}\"')
        return obj

    @classmethod
    def load_all(cls, client: CacheClient) -> list[Self]:
        return [cls.load(client, pk) for pk in client.array_values(cls._registry)]

    def pk(self) -> str:
        if isinstance(self._pk, (list, tuple, set)):
            return ':'.join([self._prefix, *(getattr(self, pk) for pk in self._pk)])
        return f'{self._prefix}:{getattr(self, self._pk)}'

    @classmethod
    def pk_all(cls, client: CacheClient):
        return client.array_values(cls._registry)

    @classmethod
    def pk_matches(cls, client: CacheClient, partial_pk: str) -> set[str]:
        return {
            value for value in client.array_values(cls._registry) if partial_pk in value
        }

    def save(self, client: CacheClient):
        mapping = generate_update_mapping(self)
        client.save(**mapping)


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

    lines: list[CachedLine] = relationship_field(many=True)
    refresh_tokens: list[CachedRefreshToken] = relationship_field(many=True)
    sessions: list[CachedSession] = relationship_field(many=True)

    @classmethod
    def from_sql(cls, user: SQLUser):
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
        return SQLUser(
            uuid=self.uuid,
            tenant_uuid=self.tenant_uuid,
            state=self.state,
            status=self.status,
        )

    def delete(self, client: CacheClient):
        for line in self.lines:
            line.delete(client)
        for refresh_token in self.refresh_tokens:
            refresh_token.delete(client)
        for session in self.sessions:
            session.delete(client)
        client.delete(self.pk())


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

    endpoint: CachedEndpoint = relationship_field(foreign_key='endpoint_name')
    channels: list[CachedChannel] = relationship_field(many=True)
    user: CachedUser = relationship_field(foreign_key='user_uuid')

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
    def from_sql(cls, line: SQLLine):
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

    user: CachedUser = relationship_field(foreign_key='user_uuid')

    @classmethod
    def from_sql(cls, session: SQLSession):
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
    _pk: ClassVar[list[str]] = ['user_uuid', 'client_id']

    client_id: str
    user_uuid: str
    mobile: bool
    tenant_uuid: str

    user: CachedUser = relationship_field(foreign_key='user_uuid')

    @classmethod
    def from_sql(cls, refresh_token: SQLRefreshToken):
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

    line: CachedLine = relationship_field(foreign_key='line_id')

    @classmethod
    def from_sql(cls, channel: SQLChannel):
        return cls(channel.name, channel.state, channel.line_id)


@dataclass
class CachedEndpoint(BaseModel):
    _registry: ClassVar[str] = 'endpoints'
    _prefix: ClassVar[str] = 'endpoint'
    _pk: ClassVar[str] = 'name'

    name: str
    state: str
    line_id: int = field(default=None)

    line: CachedLine = relationship_field(foreign_key='line_id')

    @classmethod
    def from_sql(cls, endpoint: SQLEndpoint):
        cached_endpoint = cls(endpoint.name, endpoint.state)
        if endpoint.line:
            cached_endpoint.line_id = int(endpoint.line.id)
        return cached_endpoint
