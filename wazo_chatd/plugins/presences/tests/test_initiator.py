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
        dao=mock.create_autospec(DAO(), instance=True),
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


def test_initiate_endpoints_dedupes_duplicate_devices(initiator: Initiator):
    events = [
        {'Event': 'DeviceStateChange', 'Device': 'PJSIP/abc', 'State': 'INUSE'},
        {'Event': 'DeviceStateChange', 'Device': 'PJSIP/abc', 'State': 'UNAVAILABLE'},
    ]

    with mock.patch('wazo_chatd.plugins.presences.initiator.session_scope'):
        initiator.initiate_endpoints(events)

    initiator._dao.endpoint.create_all.assert_called_once()
    (endpoints,) = initiator._dao.endpoint.create_all.call_args[0]
    assert len(endpoints) == 1
    assert endpoints[0].name == 'PJSIP/abc'
    assert endpoints[0].state == 'unavailable'


def test_initiate_channels_dedupes_duplicate_channels(initiator: Initiator):
    line = mock.Mock(id=42, endpoint_name='PJSIP/abc')
    initiator._dao.line.list_.return_value = [line]
    events = [
        {
            'Event': 'CoreShowChannel',
            'Channel': 'PJSIP/abc-00000001',
            'ChannelStateDesc': 'Up',
            'ChanVariable': {},
        },
        {
            'Event': 'CoreShowChannel',
            'Channel': 'PJSIP/abc-00000001',
            'ChannelStateDesc': 'Up',
            'ChanVariable': {},
        },
    ]

    with mock.patch('wazo_chatd.plugins.presences.initiator.session_scope'):
        initiator.initiate_channels(events)

    initiator._dao.channel.create_all.assert_called_once()
    (channels,) = initiator._dao.channel.create_all.call_args[0]
    assert len(channels) == 1
    assert channels[0].name == 'PJSIP/abc-00000001'
    assert channels[0].state == 'talking'
    assert channels[0].line_id == 42


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


def test_paginate_proxy_forwards_list_params(initiator: Initiator):
    def paginated_callback(recurse, limit, offset, view):
        return {
            'items': [{'id': offset + i} for i in range(1, limit + 1)],
            'total': limit * 3,
        }

    callback_mock = mock.Mock(side_effect=paginated_callback)
    initiator._paginate_proxy(callback_mock, limit=2, view='line_presence')

    assert callback_mock.call_count == 3
    for call in callback_mock.call_args_list:
        assert call.kwargs['view'] == 'line_presence'
        assert call.kwargs['recurse'] is True


def test_initiate_fetches_users_with_line_presence_view(initiator: Initiator):
    initiator._auth = mock.MagicMock()
    initiator._amid = mock.MagicMock()
    initiator._confd = mock.MagicMock()
    initiator._auth.token.new.return_value = {'token': 'a-token'}

    for method_name in (
        'initiate_endpoints',
        'initiate_tenants',
        'initiate_users',
        'initiate_sessions',
        'initiate_refresh_tokens',
        'initiate_channels',
        'execute_post_hooks',
    ):
        setattr(initiator, method_name, mock.Mock())

    with mock.patch.object(
        initiator, '_paginate_proxy', return_value={'items': [], 'total': 0}
    ) as paginate_proxy_mock:
        initiator.initiate()

    users_calls = [
        call
        for call in paginate_proxy_mock.call_args_list
        if call.args and call.args[0] is initiator._confd.users.list
    ]
    assert len(users_calls) == 1
    assert users_calls[0].kwargs.get('view') == 'line_presence'
