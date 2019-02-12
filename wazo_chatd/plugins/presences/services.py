# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later


class PresenceService:

    def __init__(self, user_dao, notifier):
        self._user_dao = user_dao
        self._notifier = notifier

    def list_(self, tenant_uuids, **filter_parameters):
        return self._user_dao.list_(tenant_uuids, **filter_parameters)

    def count(self, tenant_uuids, **filter_parameters):
        return self._user_dao.count(tenant_uuids, **filter_parameters)

    def get(self, tenant_uuids, user_uuid):
        return self._user_dao.get(tenant_uuids, user_uuid)

    def update(self, user):
        self._user_dao.update(user)
        self._notifier.updated(user)
        return user
