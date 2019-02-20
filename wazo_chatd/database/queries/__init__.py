# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from .device import DeviceDAO
from .line import LineDAO
from .session import SessionDAO
from .tenant import TenantDAO
from .user import UserDAO


class DAO:

    _daos = {
        'device': DeviceDAO,
        'line': LineDAO,
        'session': SessionDAO,
        'tenant': TenantDAO,
        'user': UserDAO,
    }

    def __init__(self):
        for name, dao in self._daos.items():
            setattr(self, name, dao())
