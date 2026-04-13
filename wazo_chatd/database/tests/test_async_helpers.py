# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from wazo_chatd.database.async_helpers import (
    _build_async_engine_args,
    async_session_scope,
    init_async_db,
)


class TestBuildAsyncEngineArgs(unittest.TestCase):
    def test_converts_postgresql_scheme(self) -> None:
        uri, _ = _build_async_engine_args('postgresql://user:pass@localhost/db')
        assert uri == 'postgresql+asyncpg://user:pass@localhost/db'

    def test_preserves_existing_asyncpg_scheme(self) -> None:
        uri, _ = _build_async_engine_args('postgresql+asyncpg://user:pass@localhost/db')
        assert uri == 'postgresql+asyncpg://user:pass@localhost/db'

    def test_ssl_disabled_by_default(self) -> None:
        _, connect_args = _build_async_engine_args('postgresql://localhost/db')
        assert connect_args == {'ssl': False}

    def test_sslmode_require_enables_ssl_and_is_stripped(self) -> None:
        uri, connect_args = _build_async_engine_args(
            'postgresql://localhost/db?sslmode=require'
        )
        assert connect_args == {'ssl': True}
        assert 'sslmode' not in uri

    def test_application_name_routed_to_server_settings(self) -> None:
        uri, connect_args = _build_async_engine_args(
            'postgresql://localhost/db?application_name=wazo-chatd'
        )
        assert connect_args == {
            'ssl': False,
            'server_settings': {'application_name': 'wazo-chatd'},
        }
        assert 'application_name' not in uri

    def test_multiple_known_server_settings_extracted(self) -> None:
        uri, connect_args = _build_async_engine_args(
            'postgresql://localhost/db'
            '?application_name=wazo-chatd'
            '&statement_timeout=5000'
            '&search_path=public'
        )
        assert connect_args['server_settings'] == {
            'application_name': 'wazo-chatd',
            'statement_timeout': '5000',
            'search_path': 'public',
        }
        assert 'application_name' not in uri
        assert 'statement_timeout' not in uri
        assert 'search_path' not in uri

    def test_unknown_query_params_stay_on_uri(self) -> None:
        uri, connect_args = _build_async_engine_args(
            'postgresql://localhost/db?connect_timeout=5&application_name=foo'
        )
        assert 'connect_timeout=5' in uri
        assert connect_args['server_settings'] == {'application_name': 'foo'}


class TestInitAsyncDb(unittest.TestCase):
    @patch('wazo_chatd.database.async_helpers.create_async_engine')
    def test_returns_engine_and_factory(self, mock_create: MagicMock) -> None:
        mock_engine = MagicMock()
        mock_create.return_value = mock_engine

        engine, factory = init_async_db('postgresql://localhost/db', pool_size=3)

        assert engine is mock_engine
        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert 'postgresql+asyncpg://localhost/db' in call_args.args
        assert call_args.kwargs['pool_size'] == 3

    @patch('wazo_chatd.database.async_helpers.create_async_engine')
    def test_forwards_server_settings_via_connect_args(
        self, mock_create: MagicMock
    ) -> None:
        init_async_db('postgresql://localhost/db?application_name=wazo-chatd')

        connect_args = mock_create.call_args.kwargs['connect_args']
        assert connect_args['server_settings'] == {'application_name': 'wazo-chatd'}


class TestAsyncSessionScope(unittest.IsolatedAsyncioTestCase):
    async def test_commits_on_success(self) -> None:
        session = AsyncMock()
        factory = MagicMock(return_value=session)

        async with async_session_scope(factory) as s:
            assert s is session

        session.commit.assert_awaited_once()
        session.close.assert_awaited_once()
        session.rollback.assert_not_awaited()

    async def test_rolls_back_on_error(self) -> None:
        session = AsyncMock()
        factory = MagicMock(return_value=session)

        with self.assertRaises(ValueError):
            async with async_session_scope(factory):
                raise ValueError('boom')

        session.rollback.assert_awaited_once()
        session.close.assert_awaited_once()
        session.commit.assert_not_awaited()
