# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from sqlalchemy import text
from wazo_test_helpers import until

from .helpers.base import ConnectorIntegrationTest, use_asset


@use_asset('connectors')
class TestStorePopulate(ConnectorIntegrationTest):
    def test_populate_does_not_leak_open_transaction(self):
        def store_populated():
            assert 'Populated connector store' in self.asset_cls.service_logs('chatd')

        until.assert_(store_populated, timeout=30)

        def no_leaked_transaction():
            leaked = (
                self._session.execute(
                    text(
                        "SELECT query FROM pg_stat_activity"
                        " WHERE state LIKE 'idle in transaction%'"
                        " AND query LIKE '%chatd_user_identity%'"
                    )
                )
                .scalars()
                .all()
            )
            # release our own transaction so it cannot show up as leaked
            self._session.rollback()
            assert leaked == []

        until.assert_(no_leaked_transaction, timeout=10)
