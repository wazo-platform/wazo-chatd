# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.schema import Index, UniqueConstraint
from sqlalchemy_utils import UUIDType, generic_repr

if TYPE_CHECKING:
    # NOTE(clanglois): this can be removed with sqlalchemy 2.0
    from sqlalchemy_stubs import DeclarativeMeta, RelationshipProperty


Base: type[DeclarativeMeta] = declarative_base()


@generic_repr
class Tenant(Base):  # type: ignore[misc, valid-type]
    __tablename__ = 'chatd_tenant'

    uuid = Column(UUIDType(), primary_key=True)


@generic_repr
class User(Base):  # type: ignore[misc, valid-type]
    __tablename__ = 'chatd_user'
    __table_args__ = (Index('chatd_user__idx__tenant_uuid', 'tenant_uuid'),)

    uuid = Column(UUIDType(), primary_key=True)
    tenant_uuid: UUIDType = Column(
        UUIDType(),
        ForeignKey('chatd_tenant.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    state = Column(
        String(24),
        CheckConstraint(
            "state in ('available', 'unavailable', 'invisible', 'away')",
            name='chatd_user_state_check',
        ),
        nullable=False,
    )
    status = Column(Text())
    do_not_disturb = Column(Boolean(), nullable=False, server_default='false')
    last_activity = Column(DateTime(timezone=True))

    tenant: RelationshipProperty[Tenant] = relationship('Tenant')
    sessions: RelationshipProperty[Session] = relationship(
        'Session',
        cascade='all,delete-orphan',
        passive_deletes=False,
    )
    refresh_tokens: RelationshipProperty[RefreshToken] = relationship(
        'RefreshToken',
        cascade='all,delete-orphan',
        passive_deletes=False,
    )
    lines: RelationshipProperty[Line] = relationship(
        'Line',
        cascade='all,delete-orphan',
        passive_deletes=False,
    )


@generic_repr
class Session(Base):  # type: ignore[misc, valid-type]
    __tablename__ = 'chatd_session'
    __table_args__ = (Index('chatd_session__idx__user_uuid', 'user_uuid'),)

    uuid = Column(UUIDType(), primary_key=True)
    mobile = Column(Boolean, nullable=False, default=False)
    user_uuid: UUIDType = Column(
        UUIDType(),
        ForeignKey('chatd_user.uuid', ondelete='CASCADE'),
        nullable=False,
    )

    user: RelationshipProperty[User] = relationship('User', viewonly=True)
    tenant_uuid = association_proxy('user', 'tenant_uuid')


@generic_repr
class RefreshToken(Base):  # type: ignore[misc, valid-type]
    __tablename__ = 'chatd_refresh_token'

    client_id = Column(Text, nullable=False, primary_key=True)
    user_uuid: UUIDType = Column(
        UUIDType(),
        ForeignKey('chatd_user.uuid', ondelete='CASCADE'),
        nullable=False,
        primary_key=True,
    )
    mobile = Column(Boolean, nullable=False, default=False)

    user: RelationshipProperty[User] = relationship('User', viewonly=True)
    tenant_uuid = association_proxy('user', 'tenant_uuid')


@generic_repr
class Line(Base):  # type: ignore[misc, valid-type]
    __tablename__ = 'chatd_line'
    __table_args__ = (
        Index('chatd_line__idx__user_uuid', 'user_uuid'),
        Index('chatd_line__idx__endpoint_name', 'endpoint_name'),
    )

    id = Column(Integer, primary_key=True)
    user_uuid: UUIDType = Column(
        UUIDType(),
        ForeignKey('chatd_user.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    endpoint_name = Column(Text, ForeignKey('chatd_endpoint.name', ondelete='SET NULL'))
    media = Column(
        String(24),
        CheckConstraint("media in ('audio', 'video')", name='chatd_line_media_check'),
    )
    user: RelationshipProperty[User] = relationship('User', viewonly=True)
    tenant_uuid = association_proxy('user', 'tenant_uuid')

    endpoint: RelationshipProperty[Endpoint] = relationship('Endpoint')
    endpoint_state = association_proxy('endpoint', 'state')

    channels: RelationshipProperty[Channel] = relationship(
        'Channel',
        cascade='all,delete-orphan',
        passive_deletes=False,
    )
    channels_state = association_proxy('channels', 'state')


@generic_repr
class Endpoint(Base):  # type: ignore[misc, valid-type]
    __tablename__ = 'chatd_endpoint'

    name = Column(Text, primary_key=True)
    state = Column(
        String(24),
        CheckConstraint("state in ('available', 'unavailable')"),
        nullable=False,
        default='unavailable',
    )
    line: RelationshipProperty[Line] = relationship(
        'Line',
        uselist=False,
        viewonly=True,
    )


@generic_repr
class Channel(Base):  # type: ignore[misc, valid-type]
    __tablename__ = 'chatd_channel'
    __table_args__ = (Index('chatd_channel__idx__line_id', 'line_id'),)

    name = Column(Text, primary_key=True)
    state = Column(
        String(24),
        CheckConstraint(
            "state in ('undefined', 'holding', 'ringing', 'talking', 'progressing')",
            name='chatd_channel_state_check',
        ),
        nullable=False,
        default='undefined',
    )
    line_id = Column(
        Integer, ForeignKey('chatd_line.id', ondelete='CASCADE'), nullable=False
    )

    line: RelationshipProperty[Line] = relationship('Line', viewonly=True)


@generic_repr
class Room(Base):  # type: ignore[misc, valid-type]
    __tablename__ = 'chatd_room'
    __table_args__ = (Index('chatd_room__idx__tenant_uuid', 'tenant_uuid'),)

    uuid = Column(
        UUIDType(), server_default=text('uuid_generate_v4()'), primary_key=True
    )
    name = Column(Text)
    tenant_uuid: UUIDType = Column(
        UUIDType(),
        ForeignKey('chatd_tenant.uuid', ondelete='CASCADE'),
        nullable=False,
    )

    users: RelationshipProperty[RoomUser] = relationship(
        'RoomUser',
        cascade='all,delete-orphan',
        passive_deletes=False,
    )
    messages: RelationshipProperty[RoomMessage] = relationship(
        'RoomMessage',
        cascade='all,delete-orphan',
        passive_deletes=False,
        order_by='desc(RoomMessage.created_at)',
    )


@generic_repr
class RoomUser(Base):  # type: ignore[misc, valid-type]
    __tablename__ = 'chatd_room_user'
    __table_args__ = (Index('chatd_room_user__idx__identity', 'identity'),)

    room_uuid: UUIDType = Column(
        UUIDType(),
        ForeignKey('chatd_room.uuid', ondelete='CASCADE'),
        primary_key=True,
    )
    uuid = Column(UUIDType(), primary_key=True)
    tenant_uuid = Column(UUIDType(), primary_key=True)
    wazo_uuid = Column(UUIDType(), primary_key=True)

    # External participants: "+15559876", "bob@remote.wazo.io", etc.
    # None for internal Wazo users.
    identity = Column(String, nullable=True)


@generic_repr
class RoomMessage(Base):  # type: ignore[misc, valid-type]
    __tablename__ = 'chatd_room_message'
    __table_args__ = (Index('chatd_room_message__idx__room_uuid', 'room_uuid'),)

    uuid = Column(
        UUIDType(), server_default=text('uuid_generate_v4()'), primary_key=True
    )
    room_uuid: UUIDType = Column(
        UUIDType(),
        ForeignKey('chatd_room.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    content = Column(Text)
    alias = Column(String(256))
    user_uuid = Column(UUIDType(), nullable=False)
    tenant_uuid = Column(UUIDType(), nullable=False)
    wazo_uuid = Column(UUIDType(), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("(now() at time zone 'utc')"),
        nullable=False,
    )

    room: RelationshipProperty[Room] = relationship('Room', viewonly=True)
    meta: RelationshipProperty[MessageMeta | None] = relationship(
        'MessageMeta',
        uselist=False,
        cascade='all,delete-orphan',
        back_populates='message',
    )


@generic_repr
class UserIdentity(Base):  # type: ignore[misc, valid-type]
    __tablename__ = 'chatd_user_identity'
    __table_args__ = (
        UniqueConstraint('backend', 'identity', 'type'),
        Index('chatd_user_identity__idx__tenant_uuid', 'tenant_uuid'),
        Index('chatd_user_identity__idx__user_uuid', 'user_uuid'),
    )

    uuid = Column(
        UUIDType(), server_default=text('uuid_generate_v4()'), primary_key=True
    )
    tenant_uuid: UUIDType = Column(
        UUIDType(),
        ForeignKey('chatd_tenant.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    user_uuid: UUIDType = Column(
        UUIDType(),
        ForeignKey('chatd_user.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    backend = Column(String, nullable=False)
    type_ = Column('type', String, nullable=False)
    identity = Column(String, nullable=False)
    extra = Column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    tenant: RelationshipProperty[Tenant] = relationship(
        'Tenant', uselist=False, viewonly=True
    )
    user: RelationshipProperty[User] = relationship(
        'User', uselist=False, viewonly=True
    )


@generic_repr
class MessageMeta(Base):  # type: ignore[misc, valid-type]
    __tablename__ = 'chatd_message_meta'
    __table_args__ = (
        Index(
            'chatd_message_meta__idx__extra',
            'extra',
            postgresql_using='gin',
        ),
        Index('chatd_message_meta__idx__external_id', 'external_id'),
    )

    message_uuid: UUIDType = Column(
        UUIDType(),
        ForeignKey('chatd_room_message.uuid', ondelete='CASCADE'),
        primary_key=True,
    )
    type_ = Column('type', String, nullable=True)
    backend = Column(String, nullable=True)
    sender_identity_uuid: UUIDType = Column(
        UUIDType(),
        ForeignKey('chatd_user_identity.uuid', ondelete='SET NULL'),
        nullable=True,
    )
    retry_count = Column(Integer, nullable=False, default=0, server_default='0')
    external_id = Column(String, nullable=True)
    extra = Column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    sender_identity: RelationshipProperty[UserIdentity | None] = relationship(
        'UserIdentity', uselist=False, viewonly=True
    )
    message: RelationshipProperty[RoomMessage] = relationship(
        'RoomMessage', uselist=False, back_populates='meta'
    )
    records: RelationshipProperty[list[DeliveryRecord]] = relationship(
        'DeliveryRecord',
        uselist=True,
        cascade='all,delete-orphan',
        order_by=('DeliveryRecord.timestamp', 'DeliveryRecord.id'),
    )

    @hybrid_property
    def status(self) -> str | None:
        return self.records[-1].status if self.records else None

    @status.expression  # type: ignore[no-redef]
    def status(cls):
        return (
            select(DeliveryRecord.status)
            .where(DeliveryRecord.message_uuid == cls.message_uuid)
            .order_by(DeliveryRecord.timestamp.desc(), DeliveryRecord.id.desc())
            .limit(1)
            .correlate_except(DeliveryRecord)
            .scalar_subquery()
        )

    @hybrid_property
    def updated_at(self) -> datetime | None:
        return self.records[-1].timestamp if self.records else None

    @updated_at.expression  # type: ignore[no-redef]
    def updated_at(cls):
        return (
            select(DeliveryRecord.timestamp)
            .where(DeliveryRecord.message_uuid == cls.message_uuid)
            .order_by(DeliveryRecord.timestamp.desc(), DeliveryRecord.id.desc())
            .limit(1)
            .correlate_except(DeliveryRecord)
            .scalar_subquery()
        )


@generic_repr
class DeliveryRecord(Base):  # type: ignore[misc, valid-type]
    __tablename__ = 'chatd_delivery_record'
    __table_args__ = (Index('chatd_delivery_record__idx__message_uuid', 'message_uuid'),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_uuid: UUIDType = Column(
        UUIDType(),
        ForeignKey('chatd_message_meta.message_uuid', ondelete='CASCADE'),
        nullable=False,
    )
    status = Column(String, nullable=False)
    reason = Column(String, nullable=True)
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("(now() at time zone 'utc')"),
        nullable=False,
    )
