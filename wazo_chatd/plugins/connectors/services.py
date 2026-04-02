# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from wazo_chatd.exceptions import UnknownRoomException
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry

if TYPE_CHECKING:
    from wazo_chatd.database.models import RoomUser, UserAlias
    from wazo_chatd.database.queries import DAO

logger = logging.getLogger(__name__)


class ConnectorService:
    def __init__(self, dao: DAO, registry: ConnectorRegistry) -> None:
        self._dao = dao
        self._registry = registry

    def list_room_aliases(
        self,
        tenant_uuids: list[str],
        room_uuid: str,
        user_uuid: str,
    ) -> list[UserAlias]:
        room = self._dao.room.get(tenant_uuids, room_uuid)

        if user_uuid not in {str(u.uuid) for u in room.users}:
            raise UnknownRoomException(room_uuid)

        others = [u for u in room.users if str(u.uuid) != user_uuid]
        if not others:
            return []

        reachable_types: set[str] | None = None
        for participant in others:
            participant_types = self._resolve_participant_types(participant)
            if reachable_types is None:
                reachable_types = participant_types
            else:
                reachable_types &= participant_types

        if not reachable_types:
            return []

        return self._dao.user_alias.list_by_user_and_types(
            user_uuid, sorted(reachable_types)
        )

    def _resolve_participant_types(self, participant: RoomUser) -> set[str]:
        identity = participant.identity

        if identity is not None:
            if self._dao.user_alias.is_identity_bound(identity):
                return set(
                    self._dao.user_alias.list_types_by_user(str(participant.uuid))
                )
            return self._registry.resolve_reachable_types(identity)

        return set(self._dao.user_alias.list_types_by_user(str(participant.uuid)))
