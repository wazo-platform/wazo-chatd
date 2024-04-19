from unittest import mock

import pytest
from wazo_amid_client import Client as AmidClient
from wazo_auth_client import Client as AuthClient
from wazo_confd_client import Client as ConfdClient

from wazo_chatd.database.queries import DAO
from wazo_chatd.plugins.presences.initiator import Initiator


@pytest.fixture
def initiator():
    return Initiator(
        dao=mock.create_autospec(DAO, instance=True),
        auth=mock.create_autospec(AuthClient, instance=True),
        amid=mock.create_autospec(AmidClient, instance=True),
        confd=mock.create_autospec(ConfdClient, instance=True),
    )


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
