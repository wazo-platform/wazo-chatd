# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock

from wazo_chatd.database.async_helpers import _current_session
from wazo_chatd.database.queries.async_.user_identity import AsyncUserIdentityDAO


class TestAsyncListByUser(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = AsyncMock()
        self.token = _current_session.set(self.session)
        self.dao = AsyncUserIdentityDAO()

    def tearDown(self) -> None:
        _current_session.reset(self.token)

    async def test_returns_query_results(self) -> None:
        record = Mock()
        result_mock = Mock()
        result_mock.scalars.return_value.all.return_value = [record]
        self.session.execute.return_value = result_mock

        result = await self.dao.list_by_user('user-uuid', ['twilio'])

        assert result == [record]
        self.session.execute.assert_awaited_once()

    async def test_without_backends_filter(self) -> None:
        result_mock = Mock()
        result_mock.scalars.return_value.all.return_value = []
        self.session.execute.return_value = result_mock

        result = await self.dao.list_by_user('user-uuid')

        assert result == []
        self.session.execute.assert_awaited_once()


class TestAsyncFindByIdentityAndBackend(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = AsyncMock()
        self.token = _current_session.set(self.session)
        self.dao = AsyncUserIdentityDAO()

    def tearDown(self) -> None:
        _current_session.reset(self.token)

    async def test_returns_record_when_found(self) -> None:
        record = Mock()
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = record
        self.session.execute.return_value = result_mock

        result = await self.dao.find_by_identity_and_backend('+15551234', 'twilio')

        assert result is record
        self.session.execute.assert_awaited_once()

    async def test_returns_none_when_not_found(self) -> None:
        result_mock = Mock()
        result_mock.scalar_one_or_none.return_value = None
        self.session.execute.return_value = result_mock

        result = await self.dao.find_by_identity_and_backend('+15551234', 'twilio')

        assert result is None
