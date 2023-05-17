# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from wazo_chatd.database.models import (
    Channel,
    Endpoint,
    Line,
    RefreshToken,
    Session,
    User,
)


class BaseModel(ABC):
    @classmethod
    @abstractmethod
    def from_sql(self):
        pass


@dataclass
class CachedUser(BaseModel):
    uuid: str
    tenant_uuid: str
    state: str
    status: str
    do_not_disturb: bool
    last_activity: datetime
    sessions: list[CachedSession]
    refresh_tokens: list[CachedRefreshToken]
    lines: list[CachedLine]

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
            sessions,
            refresh_tokens,
            lines,
        )


@dataclass
class CachedSession:
    uuid: str
    mobile: bool
    user_uuid: str
    tenant_uuid: str

    @classmethod
    def from_sql(cls, session: Session):
        return cls(
            str(session.uuid),
            session.mobile,
            str(session.user_uuid),
            str(session.tenant_uuid),
        )


@dataclass
class CachedRefreshToken:
    client_id: str
    user_uuid: str
    mobile: bool
    tenant_uuid: str

    @classmethod
    def from_sql(cls, refresh_token: RefreshToken):
        return cls(
            str(refresh_token.client_id),
            str(refresh_token.user_uuid),
            refresh_token.mobile,
            str(refresh_token.tenant_uuid),
        )


@dataclass
class CachedChannel:
    name: str
    state: str
    line_id: int

    @classmethod
    def from_sql(cls, channel: Channel):
        return cls(channel.name, channel.state, channel.line_id)


@dataclass
class CachedEndpoint:
    name: str
    state: str

    @classmethod
    def from_sql(cls, endpoint: Endpoint):
        return cls(endpoint.name, endpoint.state)


@dataclass
class CachedLine:
    id: int
    user_uuid: str
    endpoint_name: str
    media: str
    tenant_uuid: str
    endpoint: Optional[CachedEndpoint]
    endpoint_state: str
    channels: list[CachedChannel]
    channels_state: list[str]

    @classmethod
    def from_sql(cls, line: Line):
        endpoint = CachedEndpoint.from_sql(line.endpoint) if line.endpoint else None
        endpoint_state = getattr(endpoint, 'state', None)
        channels = [CachedChannel.from_sql(channel) for channel in line.channels]
        return cls(
            int(line.id),
            str(line.user_uuid),
            line.endpoint_name,
            line.media,
            str(line.tenant_uuid),
            endpoint,
            endpoint_state,
            channels,
            [channel.state for channel in channels],
        )
