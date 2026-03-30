# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from wazo_chatd.database.async_helpers import (
    async_session_scope,
    init_async_db,
    make_async_uri,
)


class TestMakeAsyncUri(unittest.TestCase):
    def test_converts_postgresql_scheme(self) -> None:
        result = make_async_uri('postgresql://user:pass@localhost/db')
        assert result == 'postgresql+asyncpg://user:pass@localhost/db'

    def test_already_async_unchanged(self) -> None:
        uri = 'postgresql+asyncpg://user:pass@localhost/db'
        assert make_async_uri(uri) == uri

    def test_preserves_query_params(self) -> None:
        uri = 'postgresql://user:pass@localhost/db?sslmode=require'
        result = make_async_uri(uri)
        assert result == 'postgresql+asyncpg://user:pass@localhost/db?sslmode=require'


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
