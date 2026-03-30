# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock

from wazo_chatd.database.queries.async_.user_alias import (
    find_by_identity_and_backend,
    list_by_user_and_types,
)


class TestAsyncListByUserAndTypes(unittest.IsolatedAsyncioTestCase):
    async def test_returns_query_results(self) -> None:
        alias = Mock()
        result_mock = Mock()
        result_mock.scalars.return_value.all.return_value = [alias]
        session = AsyncMock()
        session.execute.return_value = result_mock

        result = await list_by_user_and_types(session, 'user-uuid', ['sms'])

        assert result == [alias]
        session.execute.assert_awaited_once()

    async def test_without_types_filter(self) -> None:
        result_mock = Mock()
        result_mock.scalars.return_value.all.return_value = []
        session = AsyncMock()
        session.execute.return_value = result_mock

        result = await list_by_user_and_types(session, 'user-uuid')

        assert result == []
        session.execute.assert_awaited_once()


class TestAsyncFindByIdentityAndBackend(unittest.IsolatedAsyncioTestCase):
    async def test_returns_alias_when_found(self) -> None:
        alias = Mock()
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = alias
        session = AsyncMock()
        session.execute.return_value = result_mock

        result = await find_by_identity_and_backend(session, '+15551234', 'twilio')

        assert result is alias
        session.execute.assert_awaited_once()

    async def test_returns_none_when_not_found(self) -> None:
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = None
        session = AsyncMock()
        session.execute.return_value = result_mock

        result = await find_by_identity_and_backend(session, '+15551234', 'twilio')

        assert result is None
