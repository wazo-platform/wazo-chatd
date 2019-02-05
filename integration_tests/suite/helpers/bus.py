# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo_test_helpers import bus as bus_helper


class BusClient(bus_helper.BusClient):

    def send_user_created_event(self, user_uuid, tenant_uuid):
        self.publish({
            'data': {
                'uuid': user_uuid,
                'tenant_uuid': tenant_uuid,
            }
        }, 'config.user.created')

    def send_user_deleted_event(self, user_uuid, tenant_uuid):
        self.publish({
            'data': {
                'uuid': user_uuid,
                'tenant_uuid': tenant_uuid,
            }
        }, 'config.user.deleted')
