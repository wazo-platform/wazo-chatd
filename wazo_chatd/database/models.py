# Copyright 2019-2020 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy_utils import UUIDType, generic_repr

Base = declarative_base()


@generic_repr
class Tenant(Base):

    __tablename__ = 'chatd_tenant'

    uuid = Column(UUIDType(), primary_key=True)


@generic_repr
class User(Base):

    __tablename__ = 'chatd_user'

    uuid = Column(UUIDType(), primary_key=True)
    tenant_uuid = Column(
        UUIDType(),
        ForeignKey('chatd_tenant.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    state = Column(
        String(24),
        CheckConstraint("state in ('available', 'unavailable', 'invisible', 'away')"),
        nullable=False,
    )
    status = Column(Text())
    do_not_disturb = Column(Boolean(), nullable=False, server_default='false')
    last_activity = Column(DateTime())

    tenant = relationship('Tenant')
    sessions = relationship(
        'Session', cascade='all,delete-orphan', passive_deletes=False
    )
    refresh_tokens = relationship(
        'RefreshToken', cascade='all,delete-orphan', passive_deletes=False
    )
    lines = relationship('Line', cascade='all,delete-orphan', passive_deletes=False)


@generic_repr
class Session(Base):

    __tablename__ = 'chatd_session'

    uuid = Column(UUIDType(), primary_key=True)
    mobile = Column(Boolean, nullable=False, default=False)
    user_uuid = Column(
        UUIDType(),
        ForeignKey('chatd_user.uuid', ondelete='CASCADE'),
        nullable=False,
    )

    user = relationship('User', viewonly=True)
    tenant_uuid = association_proxy('user', 'tenant_uuid')


@generic_repr
class RefreshToken(Base):

    __tablename__ = 'chatd_refresh_token'

    client_id = Column(Text, nullable=False, primary_key=True)
    user_uuid = Column(
        UUIDType(),
        ForeignKey('chatd_user.uuid', ondelete='CASCADE'),
        nullable=False,
        primary_key=True,
    )
    mobile = Column(Boolean, nullable=False, default=False)

    user = relationship('User', viewonly=True)
    tenant_uuid = association_proxy('user', 'tenant_uuid')


@generic_repr
class Line(Base):

    __tablename__ = 'chatd_line'

    id = Column(Integer, primary_key=True)
    user_uuid = Column(UUIDType(), ForeignKey('chatd_user.uuid', ondelete='CASCADE'))
    endpoint_name = Column(Text, ForeignKey('chatd_endpoint.name', ondelete='SET NULL'))
    media = Column(String(24), CheckConstraint("media in ('audio', 'video')"))
    user = relationship('User', viewonly=True)
    tenant_uuid = association_proxy('user', 'tenant_uuid')

    endpoint = relationship('Endpoint')
    endpoint_state = association_proxy('endpoint', 'state')

    channels = relationship(
        'Channel', cascade='all,delete-orphan', passive_deletes=False
    )
    channels_state = association_proxy('channels', 'state')


@generic_repr
class Endpoint(Base):

    __tablename__ = 'chatd_endpoint'

    name = Column(Text, primary_key=True)
    state = Column(
        String(24),
        CheckConstraint("state in ('available', 'unavailable')"),
        nullable=False,
        default='unavailable',
    )
    line = relationship('Line', uselist=False, viewonly=True)


@generic_repr
class Channel(Base):

    __tablename__ = 'chatd_channel'

    name = Column(Text, primary_key=True)
    state = Column(
        String(24),
        CheckConstraint(
            "state in ('undefined', 'holding', 'ringing', 'talking', 'progressing')"
        ),
        nullable=False,
        default='undefined',
    )
    line_id = Column(
        Integer, ForeignKey('chatd_line.id', ondelete='CASCADE'), nullable=False
    )

    line = relationship('Line', viewonly=True)


@generic_repr
class Room(Base):

    __tablename__ = 'chatd_room'

    uuid = Column(
        UUIDType(), server_default=text('uuid_generate_v4()'), primary_key=True
    )
    name = Column(Text)
    tenant_uuid = Column(
        UUIDType(),
        ForeignKey('chatd_tenant.uuid', ondelete='CASCADE'),
        nullable=False,
    )

    users = relationship('RoomUser', cascade='all,delete-orphan', passive_deletes=False)
    messages = relationship(
        'RoomMessage',
        cascade='all,delete-orphan',
        passive_deletes=False,
        order_by='desc(RoomMessage.created_at)',
    )


@generic_repr
class RoomUser(Base):

    __tablename__ = 'chatd_room_user'

    room_uuid = Column(
        UUIDType(),
        ForeignKey('chatd_room.uuid', ondelete='CASCADE'),
        primary_key=True,
    )
    uuid = Column(UUIDType(), primary_key=True)
    tenant_uuid = Column(UUIDType(), primary_key=True)
    wazo_uuid = Column(UUIDType(), primary_key=True)


@generic_repr
class RoomMessage(Base):

    __tablename__ = 'chatd_room_message'

    uuid = Column(
        UUIDType(), server_default=text('uuid_generate_v4()'), primary_key=True
    )
    room_uuid = Column(
        UUIDType(),
        ForeignKey('chatd_room.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    content = Column(Text)
    alias = Column(String(256))
    user_uuid = Column(UUIDType(), nullable=False)
    tenant_uuid = Column(UUIDType(), nullable=False)
    wazo_uuid = Column(UUIDType(), nullable=False)
    created_at = Column(DateTime(), default=datetime.datetime.utcnow, nullable=False)

    room = relationship('Room', viewonly=True)
