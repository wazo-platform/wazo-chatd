# Copyright 2019-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_test_helpers.wait_strategy import (
    ComponentsWaitStrategy as _ComponentsWaitStrategy,
)
from wazo_test_helpers.wait_strategy import NoWaitStrategy

__all__ = ['NoWaitStrategy']


class ComponentsWaitStrategy(_ComponentsWaitStrategy):
    def get_status(self, integration_test):
        return integration_test.chatd.status.get()


class PresenceInitOkWaitStrategy(ComponentsWaitStrategy):
    def __init__(self):
        super().__init__(
            [
                'presence_initialization',
                'rest_api',
                'bus_consumer',
            ]
        )


class EverythingOkWaitStrategy(ComponentsWaitStrategy):
    def __init__(self):
        super().__init__(
            [
                # 'presence_initialization',  # disabled for non-related init tests
                'rest_api',
                'bus_consumer',
                'master_tenant',
            ]
        )
