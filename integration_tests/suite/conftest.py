# Copyright 2020-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from wazo_test_helpers.pytest_asset import (
    asset_fixture,
    enable_mark_logs_fixture,
    register,
)

from .helpers import base as asset


def pytest_configure(config):
    register(config)


base = asset_fixture(asset.APIAssetLaunchingTestCase)
initialization = asset_fixture(asset.InitAssetLaunchingTestCase)
database = asset_fixture(asset.DBAssetLaunchingTestCase)
teams = asset_fixture(asset.TeamsAssetLaunchingTestCase)
connectors = asset_fixture(asset.ConnectorAssetLaunchingTestCase)
connectors_polling = asset_fixture(asset.PollingConnectorAssetLaunchingTestCase)

mark_logs = enable_mark_logs_fixture()
