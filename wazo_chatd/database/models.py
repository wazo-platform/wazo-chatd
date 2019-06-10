# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
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
from sqlalchemy.types import TypeDecorator

Base = declarative_base()

UUID_LENGTH = 36


class UUIDAsString(TypeDecorator):
    impl = String

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = str(value)
        return value


class Tenant(Base):

    __tablename__ = 'chatd_tenant'

    uuid = Column(UUIDAsString(UUID_LENGTH), primary_key=True)

    def __repr__(self):
        return "<Tenant(uuid='{uuid}')>".format(uuid=self.uuid)


class User(Base):

    __tablename__ = 'chatd_user'

    uuid = Column(UUIDAsString(UUID_LENGTH), primary_key=True)
    tenant_uuid = Column(
        UUIDAsString(UUID_LENGTH),
        ForeignKey('chatd_tenant.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    state = Column(
        String(24),
        CheckConstraint("state in ('available', 'unavailable', 'invisible')"),
        nullable=False,
    )
    status = Column(Text())
    last_activity = Column(DateTime())

    tenant = relationship('Tenant')
    sessions = relationship(
        'Session',
        cascade='all,delete-orphan',
        passive_deletes=False,
    )
    lines = relationship(
        'Line',
        cascade='all,delete-orphan',
        passive_deletes=False,
    )

    def __repr__(self):
        return (
            "<User(uuid='{uuid}', state='{state}', status='{status}',"
            "lines='{lines}', sessions='{sessions}')>"
        ).format(
            uuid=self.uuid,
            state=self.state,
            status=self.status,
            lines=self.lines,
            sessions=self.sessions,
        )


class Session(Base):

    __tablename__ = 'chatd_session'

    uuid = Column(UUIDAsString(UUID_LENGTH), primary_key=True)
    mobile = Column(Boolean, nullable=False, default=False)
    user_uuid = Column(
        UUIDAsString(UUID_LENGTH),
        ForeignKey('chatd_user.uuid', ondelete='CASCADE'),
        nullable=False,
    )

    user = relationship('User', viewonly=True)
    tenant_uuid = association_proxy('user', 'tenant_uuid')

    def __repr__(self):
        return "<Session(uuid='{uuid}', mobile='{mobile}')>".format(uuid=self.uuid, mobile=self.mobile)


class Line(Base):

    __tablename__ = 'chatd_line'

    id = Column(Integer, primary_key=True)
    user_uuid = Column(
        UUIDAsString(UUID_LENGTH),
        ForeignKey('chatd_user.uuid', ondelete='CASCADE'),
    )
    endpoint_name = Column(
        Text,
        ForeignKey('chatd_endpoint.name', ondelete='SET NULL'),
    )
    media = Column(
        String(24),
        CheckConstraint("state in ('audio', 'video')"),
    )
    user = relationship('User', viewonly=True)
    tenant_uuid = association_proxy('user', 'tenant_uuid')

    endpoint = relationship('Endpoint')
    state = association_proxy('endpoint', 'state')

    def __repr__(self):
        return "<Line(id='{id}', media='{media}', endpoint='{endpoint}')>".format(
            id=self.id,
            media=self.media,
            endpoint=self.endpoint,
        )


class Endpoint(Base):

    __tablename__ = 'chatd_endpoint'

    name = Column(Text, primary_key=True)
    state = Column(
        String(24),
        CheckConstraint("media in ('available', 'unavailable', 'holding', 'ringing', 'talking')"),
        nullable=False,
        default='unavailable',
    )

    line = relationship('Line', uselist=False, viewonly=True)

    def __repr__(self):
        return "<Endpoint(name='{name}', state='{state}')>".format(
            name=self.name,
            state=self.state,
        )


class Room(Base):

    __tablename__ = 'chatd_room'

    uuid = Column(String(UUID_LENGTH), server_default=text('uuid_generate_v4()'), primary_key=True)
    name = Column(Text)
    tenant_uuid = Column(
        UUIDAsString(UUID_LENGTH),
        ForeignKey('chatd_tenant.uuid', ondelete='CASCADE'),
        nullable=False,
    )

    users = relationship(
        'RoomUser',
        cascade='all,delete-orphan',
        passive_deletes=False,
    )
    messages = relationship(
        'RoomMessage',
        cascade='all,delete-orphan',
        passive_deletes=False,
        order_by='desc(RoomMessage.created_at)',
    )

    def __repr__(self):
        return "<Room(uuid='{uuid}', name='{name}', users='{users}', messages='{messages}')>".format(
            uuid=self.uuid,
            name=self.name,
            users=self.users,
            messages=self.messages,
        )


class RoomUser(Base):

    __tablename__ = 'chatd_room_user'

    room_uuid = Column(
        String(UUID_LENGTH),
        ForeignKey('chatd_room.uuid', ondelete='CASCADE'),
        primary_key=True,
    )
    uuid = Column(String(UUID_LENGTH), primary_key=True)
    tenant_uuid = Column(String(UUID_LENGTH), primary_key=True)
    wazo_uuid = Column(String(UUID_LENGTH), primary_key=True)

    def __repr__(self):
        return "<RoomUser(uuid='{}', tenant_uuid='{}', wazo_uuid='{}')>".format(
            self.uuid,
            self.tenant_uuid,
            self.wazo_uuid,
        )


class RoomMessage(Base):

    __tablename__ = 'chatd_room_message'

    uuid = Column(String(UUID_LENGTH), server_default=text('uuid_generate_v4()'), primary_key=True)
    room_uuid = Column(
        String(UUID_LENGTH),
        ForeignKey('chatd_room.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    content = Column(Text)
    alias = Column(String(256))
    user_uuid = Column(String(UUID_LENGTH), nullable=False)
    tenant_uuid = Column(String(UUID_LENGTH), nullable=False)
    wazo_uuid = Column(String(UUID_LENGTH), nullable=False)
    created_at = Column(DateTime(), default=datetime.datetime.utcnow, nullable=False)

    room = relationship(
        'Room',
        viewonly=True,
    )

    def __repr__(self):
        return "<RoomMessage(uuid='{uuid}', content='{content}', alias='{alias}')>".format(
            uuid=self.uuid,
            content=self.content,
            alias=self.alias,
        )
