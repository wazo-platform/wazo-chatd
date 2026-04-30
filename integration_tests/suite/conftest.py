# Copyright 2020-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
from collections.abc import Callable

import pytest
from wazo_test_helpers.asset_launching_test_case import AssetLaunchingTestCase

from .helpers import base as asset

logger = logging.getLogger(__name__)

_teardowns: dict[str, Callable[[], None]] = {}
_teardown_failures: list[tuple[str, BaseException]] = []


def pytest_collection_modifyitems(session, config, items):
    # item == test method
    # item.parent == test class
    # item.parent.own_markers == pytest markers of the test class
    # item.parent.own_markers[0].args[0] == name of the asset
    # It also remove the run-order pytest feature (--ff, --nf)
    items.sort(key=lambda item: item.parent.own_markers[0].args[0])


def _marker_of(item) -> str | None:
    if not item.parent.own_markers:
        return None
    return item.parent.own_markers[0].args[0]


def _setup(marker: str, asset_class: type[AssetLaunchingTestCase]) -> None:
    asset_class.setUpClass()
    _teardowns[marker] = asset_class.tearDownClass


def _teardown(marker: str) -> None:
    if teardown := _teardowns.pop(marker, None):
        teardown()


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item, nextitem) -> None:
    # Eagerly tear down the active asset at marker-group boundaries; the
    # session-scoped fixture's finally still handles the very last asset.
    # Swallow errors here so a teardown failure can't abort the next test's
    # setup; the fixture-finally path lets exceptions propagate so they
    # surface in pytest's error summary.
    if nextitem is None:
        return
    current = _marker_of(item)
    upcoming = _marker_of(nextitem)
    if current is not None and current != upcoming:
        try:
            _teardown(current)
        except Exception as exc:
            logger.exception('Failed to tear down asset for marker %r', current)
            _teardown_failures.append((current, exc))


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    for marker, exc in _teardown_failures:
        terminalreporter.write_sep(
            '!', f'Asset teardown failed for marker {marker!r}: {exc}'
        )


@pytest.fixture(scope='session')
def base():
    _setup('base', asset.APIAssetLaunchingTestCase)
    try:
        yield
    finally:
        _teardown('base')


@pytest.fixture(scope='session')
def initialization():
    _setup('initialization', asset.InitAssetLaunchingTestCase)
    try:
        yield
    finally:
        _teardown('initialization')


@pytest.fixture(scope='session')
def database():
    _setup('database', asset.DBAssetLaunchingTestCase)
    try:
        yield
    finally:
        _teardown('database')


@pytest.fixture(scope='session')
def teams():
    _setup('teams', asset.TeamsAssetLaunchingTestCase)
    try:
        yield
    finally:
        _teardown('teams')


@pytest.fixture(autouse=True, scope='function')
def mark_logs(request):
    test_name = f'{request.cls.__name__}.{request.function.__name__}'
    request.cls.asset_cls.mark_logs_test_start(test_name)
    yield
    request.cls.asset_cls.mark_logs_test_end(test_name)
