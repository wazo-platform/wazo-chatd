# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import requests

from hamcrest import assert_that, has_entries

from xivo_test_helpers import until


class WaitStrategy:
    def wait(self, setupd):
        raise NotImplementedError()


class NoWaitStrategy(WaitStrategy):
    def wait(self, chatd):
        pass


class EverythingOkWaitStrategy(WaitStrategy):
    def wait(self, integration_test):
        def is_ready():
            try:
                status = integration_test.chatd.status.get()
            except requests.RequestException:
                status = {}
            assert_that(
                status,
                has_entries(
                    {
                        'rest_api': has_entries(status='ok'),
                        'bus_consumer': has_entries(status='ok'),
                    }
                ),
            )

        until.assert_(is_ready, tries=60)


class RestApiOkWaitStrategy(WaitStrategy):
    def wait(self, integration_test):
        def is_ready():
            try:
                status = integration_test.chatd.status.get()
            except requests.RequestException:
                status = {}
            assert_that(status, has_entries({'rest_api': has_entries(status='ok')}))

        until.assert_(is_ready, tries=60)


class PresenceInitOkWaitStrategy(WaitStrategy):
    def wait(self, integration_test):
        def is_ready():
            try:
                status = integration_test.chatd.status.get()
            except requests.RequestException:
                status = {}
            assert_that(
                status,
                has_entries(
                    {
                        'presence_initialization': has_entries(status='ok'),
                        'rest_api': has_entries(status='ok'),
                        'bus_consumer': has_entries(status='ok'),
                    }
                ),
            )

        until.assert_(is_ready, tries=60)
