# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    # Integer,
    String,
    Text,
)
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

Base = declarative_base()


class UUIDAsString(TypeDecorator):
    impl = String

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = str(value)
        return value


class Tenant(Base):

    __tablename__ = 'chatd_tenant'

    uuid = Column(UUIDAsString(36), primary_key=True)


class User(Base):

    __tablename__ = 'chatd_user'

    uuid = Column(UUIDAsString(36), primary_key=True)
    tenant_uuid = Column(
        UUIDAsString(36),
        ForeignKey('chatd_tenant.uuid', ondelete='CASCADE'),
        nullable=False,
    )
    state = Column(
        String(24),
        CheckConstraint("state in ('available', 'unavailable', 'invisible')"),
        nullable=False,
    )
    status = Column(Text())

    tenant = relationship('Tenant')
    sessions = relationship(
        'Session',
        passive_deletes=False,
        cascade='all,delete-orphan',
    )


class Session(Base):

    __tablename__ = 'chatd_session'

    uuid = Column(UUIDAsString(36), primary_key=True)
    mobile = Column(Boolean, nullable=False, default=False)
    user_uuid = Column(
        UUIDAsString(36),
        ForeignKey('chatd_user.uuid', ondelete='CASCADE'),
        nullable=False,
    )

    user = relationship('User', viewonly=True)
    tenant_uuid = association_proxy('user', 'tenant_uuid')
