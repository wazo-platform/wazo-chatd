# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from sqlalchemy import and_, text

from ...exceptions import UnknownDeviceException
from ..helpers import get_dao_session
from ..models import Device


class DeviceDAO:

    @property
    def session(self):
        return get_dao_session()

    def create(self, device):
        self.session.add(device)
        self.session.flush()
        return device

    def find_by(self, **kwargs):
        return self._find_by(**kwargs)

    def get_by(self, **kwargs):
        device = self._find_by(**kwargs)
        if not device:
            raise UnknownDeviceException(kwargs.get('name'))
        return device

    def _find_by(self, **kwargs):
        filter_ = text('true')

        if 'name' in kwargs:
            filter_ = and_(filter_, Device.name == kwargs['name'])

        return self.session.query(Device).filter(filter_).first()

    def list_(self):
        return self.session.query(Device).all()

    def update(self, device):
        self.session.add(device)
        self.session.flush()

    def delete_all(self):
        self.session.query(Device).delete()
        self.session.flush()
