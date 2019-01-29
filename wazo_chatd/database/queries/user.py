# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy import text

from ...exceptions import UnknownUserException, UnknownUsersException
from ..helpers import get_dao_session
from ..models import User


class UserDAO:

    @property
    def session(self):
        return get_dao_session()

    def create(self, user):
        self.session.add(user)
        self.session.flush()
        return user

    def update(self, user):
        self.session.add(user)
        self.session.flush()

    def get(self, tenant_uuids, user_uuid):
        query = self.session.query(User).filter(
            User.tenant_uuid.in_(tenant_uuids),
            User.uuid == str(user_uuid),
        )

        user = query.first()
        if not user:
            raise UnknownUserException(user_uuid)
        return user

    def list_(self, tenant_uuids, uuids=None, **filter_parameters):
        users = self._get_users_query(
            tenant_uuids, uuids=uuids, **filter_parameters
        ).all()

        if uuids:
            found_uuids = set([user.uuid for user in users])
            given_uuids = set(uuids)
            if len(found_uuids) != len(given_uuids):
                raise UnknownUsersException(list(given_uuids - found_uuids))

        return users

    def count(self, tenant_uuids, **filter_parameters):
        return self._get_users_query(
            tenant_uuids, **filter_parameters
        ).count()

    def delete(self, user):
        self.session.delete(user)
        self.session.flush()

    def _get_users_query(self, tenant_uuids=None, uuids=None):
        query = self.session.query(User)

        if uuids:
            query = query.filter(User.uuid.in_(uuids))

        if tenant_uuids is None:
            return query

        if not tenant_uuids:
            return query.filter(text('false'))

        return query.filter(User.tenant_uuid.in_(tenant_uuids))
