# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from functools import wraps

from wazo_chatd.database.models import (
    User,
    Session,
    Tenant,
)

from ..base import MASTER_TENANT_UUID


def user(**user_args):
    def decorator(decorated):
        @wraps(decorated)
        def wrapper(self, *args, **kwargs):
            user_args.setdefault('uuid', str(uuid.uuid4()))
            user_args.setdefault('tenant_uuid', MASTER_TENANT_UUID)
            user_args.setdefault('state', 'unavailable')
            model = User(**user_args)

            user = self._user_dao.create(model)

            self._session.commit()
            args = list(args) + [user]
            try:
                result = decorated(self, *args, **kwargs)
            finally:
                user = self._session.query(User).get(user_args['uuid'])
                if user:
                    self._user_dao.delete(user)
                self._session.commit()
            return result
        return wrapper
    return decorator


def session(**session_args):
    def decorator(decorated):
        @wraps(decorated)
        def wrapper(self, *args, **kwargs):
            session_args.setdefault('uuid', str(uuid.uuid4()))
            session = Session(**session_args)

            self._session.add(session)
            self._session.flush()

            self._session.commit()
            args = list(args) + [session]
            try:
                result = decorated(self, *args, **kwargs)
            finally:
                session = self._session.query(Session).get(session_args['uuid'])
                if session:
                    self._session.delete(session)
                    self._session.flush()
                self._session.commit()
            return result
        return wrapper
    return decorator


def tenant(**tenant_args):
    def decorator(decorated):
        @wraps(decorated)
        def wrapper(self, *args, **kwargs):
            tenant_args.setdefault('uuid', str(uuid.uuid4()))
            model = Tenant(**tenant_args)

            tenant = self._tenant_dao.create(model)

            self._session.commit()
            args = list(args) + [tenant]
            try:
                result = decorated(self, *args, **kwargs)
            finally:
                tenant = self._session.query(Tenant).get(tenant_args['uuid'])
                if tenant:
                    self._tenant_dao.delete(tenant)
                self._session.commit()
            return result
        return wrapper
    return decorator
