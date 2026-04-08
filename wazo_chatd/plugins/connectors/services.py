# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from wazo_chatd.exceptions import UnknownRoomException
from wazo_chatd.plugins.connectors.exceptions import (
    InvalidIdentityError,
    NoCommonConnectorError,
    UnreachableParticipantError,
)
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry

if TYPE_CHECKING:
    from wazo_chatd.database.models import Room, RoomMessage, RoomUser, UserIdentity
    from wazo_chatd.database.queries import DAO

logger = logging.getLogger(__name__)


class ConnectorService:
    def __init__(self, dao: DAO, registry: ConnectorRegistry) -> None:
        self._dao = dao
        self._registry = registry

    def list_identities(
        self, tenant_uuids: list[str], user_uuid: str
    ) -> list[UserIdentity]:
        return self._dao.user_identity.list_by_user(
            user_uuid, tenant_uuids=tenant_uuids
        )

    def get_identity(
        self,
        tenant_uuids: list[str],
        identity_uuid: str,
        user_uuid: str | None = None,
    ) -> UserIdentity:
        return self._dao.user_identity.get(
            tenant_uuids, identity_uuid, user_uuid=user_uuid
        )

    def create_identity(self, identity: UserIdentity) -> UserIdentity:
        return self._dao.user_identity.create(identity)

    def update_identity(self, identity: UserIdentity) -> UserIdentity:
        self._dao.user_identity.update(identity)
        return identity

    def delete_identity(self, identity: UserIdentity) -> None:
        self._dao.user_identity.delete(identity)

    def create_outbound_delivery(
        self,
        message: RoomMessage,
        sender_identity_uuid: UUID,
    ) -> None:
        self._dao.room.create_pending_delivery(message, sender_identity_uuid)

    def list_room_identities(
        self,
        tenant_uuids: list[str],
        room_uuid: str,
        user_uuid: str,
    ) -> list[UserIdentity]:
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

        backends = self._registry.backends_for_types(reachable_types)
        return self._dao.user_identity.list_by_user(user_uuid, backends=backends)

    def validate_room_reachability(self, room: Room) -> None:
        participants = room.users
        if len(participants) < 2:
            return

        external = [u for u in participants if u.identity]
        if not external:
            return

        needs_db_lookup: list[RoomUser] = []

        external_identities = [str(u.identity) for u in external]
        bound_identities = (
            self._dao.user_identity.list_bound_identities(external_identities)
            if external_identities
            else set()
        )

        types_by_participant: dict[str, set[str]] = {}

        for user in external:
            identity = str(user.identity)
            if identity in bound_identities:
                needs_db_lookup.append(user)
            else:
                reachable = self._registry.resolve_reachable_types(identity)
                if not reachable:
                    raise UnreachableParticipantError(identity)
                types_by_participant[str(user.uuid)] = reachable

        internal = [u for u in participants if not u.identity]
        needs_db_lookup.extend(internal)

        if needs_db_lookup:
            db_backends = self._dao.user_identity.list_backends_by_users(
                [str(u.uuid) for u in needs_db_lookup]
            )
            for user in needs_db_lookup:
                user_backends = db_backends.get(str(user.uuid), set())
                if not user_backends:
                    raise UnreachableParticipantError(str(user.identity or user.uuid))
                user_types: set[str] = set()
                for backend in user_backends:
                    user_types |= self._registry.types_for_backend(backend)
                types_by_participant[str(user.uuid)] = user_types

        common_types: set[str] | None = None
        for types in types_by_participant.values():
            if common_types is None:
                common_types = types
            else:
                common_types &= types

        if not common_types:
            raise NoCommonConnectorError()

    def validate_identity_reachability(
        self,
        room: Room,
        sender_uuid: str,
        sender_identity_uuid: UUID,
    ) -> None:
        record = self._dao.user_identity.find(str(sender_identity_uuid))
        if not record:
            raise InvalidIdentityError(str(sender_identity_uuid))

        sender_backend = str(record.backend)
        sender_types = self._registry.types_for_backend(sender_backend)
        others = [u for u in room.users if str(u.uuid) != sender_uuid]

        internal = [u for u in others if not u.identity]
        external = [u for u in others if u.identity]

        if internal:
            internal_backends = self._dao.user_identity.list_backends_by_users(
                [str(u.uuid) for u in internal]
            )
            for user in internal:
                user_backends = internal_backends.get(str(user.uuid), set())
                user_types: set[str] = set()
                for backend in user_backends:
                    user_types |= self._registry.types_for_backend(backend)
                if not (sender_types & user_types):
                    raise UnreachableParticipantError(str(user.uuid), sender_backend)

        for user in external:
            reachable_types = self._registry.resolve_reachable_types(str(user.identity))
            if not (sender_types & reachable_types):
                raise UnreachableParticipantError(str(user.identity), sender_backend)

    def _resolve_participant_types(self, participant: RoomUser) -> set[str]:
        identity = participant.identity

        if identity is not None:
            if self._dao.user_identity.is_identity_bound(identity):
                user_id = str(participant.uuid)
                backends_map = self._dao.user_identity.list_backends_by_users([user_id])
                types: set[str] = set()
                for backend in backends_map.get(user_id, set()):
                    types |= self._registry.types_for_backend(backend)
                return types
            return self._registry.resolve_reachable_types(identity)

        user_id = str(participant.uuid)
        backends_map = self._dao.user_identity.list_backends_by_users([user_id])
        types = set()
        for backend in backends_map.get(user_id, set()):
            types |= self._registry.types_for_backend(backend)
        return types
