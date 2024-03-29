# Copyright 2020-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from .helpers import base as asset


def pytest_collection_modifyitems(session, config, items):
    # item == test method
    # item.parent == test class
    # item.parent.own_markers == pytest markers of the test class
    # item.parent.own_markers[0].args[0] == name of the asset
    # It also remove the run-order pytest feature (--ff, --nf)
    items.sort(key=lambda item: item.parent.own_markers[0].args[0])


@pytest.fixture(scope='session')
def base():
    asset.APIAssetLaunchingTestCase.setUpClass()
    try:
        yield
    finally:
        asset.APIAssetLaunchingTestCase.tearDownClass()


@pytest.fixture(scope='session')
def initialization():
    asset.InitAssetLaunchingTestCase.setUpClass()
    try:
        yield
    finally:
        asset.InitAssetLaunchingTestCase.tearDownClass()


@pytest.fixture(scope='session')
def database():
    asset.DBAssetLaunchingTestCase.setUpClass()
    try:
        yield
    finally:
        asset.DBAssetLaunchingTestCase.tearDownClass()


@pytest.fixture(scope='session')
def teams():
    asset.TeamsAssetLaunchingTestCase.setUpClass()
    try:
        yield
    finally:
        asset.TeamsAssetLaunchingTestCase.tearDownClass()


@pytest.fixture(autouse=True, scope='function')
def mark_logs(request):
    test_name = f'{request.cls.__name__}.{request.function.__name__}'
    request.cls.asset_cls.mark_logs_test_start(test_name)
    yield
    request.cls.asset_cls.mark_logs_test_end(test_name)
