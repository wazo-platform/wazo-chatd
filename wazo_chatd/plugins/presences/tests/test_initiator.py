# Copyright 2025-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import mock

import pytest
from wazo_amid_client import Client as AmidClient
from wazo_auth_client import Client as AuthClient
from wazo_confd_client import Client as ConfdClient

from wazo_chatd.database.queries import DAO
from wazo_chatd.plugins.presences.initiator import (
    Initiator,
    extract_endpoint_from_line,
    extract_endpoint_from_line_presence_view,
)


@pytest.fixture
def initiator():
    return Initiator(
        dao=mock.create_autospec(DAO, instance=True),
        auth=mock.create_autospec(AuthClient, instance=True),
        amid=mock.create_autospec(AmidClient, instance=True),
        confd=mock.create_autospec(ConfdClient, instance=True),
        token_expiration=10,
    )


@pytest.mark.parametrize(
    'protocol, expected',
    [
        ('sip', 'PJSIP/line-name'),
        ('sccp', 'SCCP/line-name'),
        ('custom', 'line-name'),
        ('unknown', None),
    ],
)
def test_extract_endpoint_from_line_presence_view(protocol, expected):
    line = {'name': 'line-name', 'protocol': protocol}
    assert extract_endpoint_from_line_presence_view(line) == expected


def test_extract_endpoint_from_line_presence_view_without_name():
    assert extract_endpoint_from_line_presence_view({'name': None}) is None


@pytest.mark.parametrize(
    'endpoint_key, expected',
    [
        ('endpoint_sip', 'PJSIP/line-name'),
        ('endpoint_sccp', 'SCCP/line-name'),
        ('endpoint_custom', 'line-name'),
    ],
)
def test_extract_endpoint_from_line(endpoint_key, expected):
    line = {'name': 'line-name', endpoint_key: {'id': 1}}
    assert extract_endpoint_from_line(line) == expected


def test_extract_endpoint_from_line_without_name():
    assert extract_endpoint_from_line({'name': None}) is None


def test_extract_endpoint_from_line_without_endpoint():
    assert extract_endpoint_from_line({'name': 'line-name'}) is None


def test_paginate_proxy(initiator: Initiator):
    def paginated_callback(recurse, limit, offset):
        return {
            'items': [{'id': offset + i} for i in range(1, limit + 1)],
            'total': limit * 5,
        }

    callback_mock = mock.Mock(side_effect=paginated_callback)
    results = initiator._paginate_proxy(callback_mock, limit=2)
    assert results == {
        'items': [
            {'id': 1},
            {'id': 2},
            {'id': 3},
            {'id': 4},
            {'id': 5},
            {'id': 6},
            {'id': 7},
            {'id': 8},
            {'id': 9},
            {'id': 10},
        ],
        'total': 10,
    }
    assert callback_mock.call_count == 5
