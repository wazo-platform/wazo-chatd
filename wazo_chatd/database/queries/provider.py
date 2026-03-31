# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from wazo_chatd.database.models import ChatProvider

if TYPE_CHECKING:
    from collections.abc import Callable


class ProviderDAO:
    def __init__(self, session: Callable[[], Session]) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        return self._session()

    def list_(
        self,
        tenant_uuids: list[str] | None = None,
    ) -> list[ChatProvider]:
        query = self.session.query(ChatProvider)
        if tenant_uuids:
            query = query.filter(ChatProvider.tenant_uuid.in_(tenant_uuids))
        return query.all()

    def get(self, provider_uuid: str) -> ChatProvider | None:
        return (
            self.session.query(ChatProvider)
            .filter(ChatProvider.uuid == provider_uuid)
            .first()
        )
