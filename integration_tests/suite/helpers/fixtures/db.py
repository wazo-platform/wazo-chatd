# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import uuid

from functools import wraps
from sqlalchemy import inspect

from wazo_chatd.database.models import (
    User,
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
                if inspect(user).persistent:
                    self._user_dao.delete(user)
                self._session.commit()
            return result
        return wrapper
    return decorator
