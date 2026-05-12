# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from requests.exceptions import HTTPError, RequestException

from wazo_chatd.exceptions import UnknownRoomException, UnknownUserException
from wazo_chatd.plugin_helpers.tenant import make_uuid5
from wazo_chatd.plugins.connectors.exceptions import (
    AuthServiceUnavailableException,
    InvalidIdentityException,
    InvalidIdentityFormatException,
    NoCommonConnectorException,
    UnknownBackendException,
    UnreachableParticipantException,
)
from wazo_chatd.plugins.connectors.executor import generate_message_signature
from wazo_chatd.plugins.connectors.notifier import UserIdentityNotifier
from wazo_chatd.plugins.connectors.registry import ConnectorRegistry

if TYPE_CHECKING:
    from wazo_auth_client import Client as AuthClient

    from wazo_chatd.database.models import (
        Room,
        RoomMessage,
        RoomUser,
        User,
        UserIdentity,
    )
    from wazo_chatd.database.queries import DAO

logger = logging.getLogger(__name__)


class ConnectorService:
    def __init__(
        self,
        dao: DAO,
        registry: ConnectorRegistry,
        notifier: UserIdentityNotifier,
        auth_client: AuthClient,
    ) -> None:
        self._dao = dao
        self._registry = registry
        self._notifier = notifier
        self._auth_client = auth_client

    def get_user_tenant_uuid(self, tenant_uuids: Iterable[str], user_uuid: str) -> str:
        visible_tenants = list(tenant_uuids)
        try:
            user = self._dao.user.get(visible_tenants, user_uuid)
            return str(user.tenant_uuid)
        except UnknownUserException:
            logger.debug(
                'User %s not in wazo-chatd cache, querying wazo-auth', user_uuid
            )

        try:
            user_data = self._auth_client.users.get(user_uuid)
            tenant_uuid = str(user_data['tenant_uuid'])
        except HTTPError as e:
            if (status := getattr(e.response, 'status_code', None)) == 404:
                raise UnknownUserException(user_uuid)
            logger.error('wazo-auth returned HTTP %s for user %s', status, user_uuid)
            raise AuthServiceUnavailableException()
        except RequestException:
            raise AuthServiceUnavailableException()

        if tenant_uuid not in visible_tenants:
            raise UnknownUserException(user_uuid)

        self._dao.user_identity.ensure_tenant_and_user_exist(tenant_uuid, user_uuid)
        return tenant_uuid

    def resolve_users_by_identities(self, identities: Iterable[str]) -> dict[str, User]:
        return self._dao.user_identity.resolve_users_by_identities(identities)

    def resolve_room_participants(self, body: dict, tenant_uuid: str) -> None:
        users = body.get('users', [])
        to_resolve = [u for u in users if u.get('identity') and not u.get('uuid')]
        if not to_resolve:
            return

        identities = {u['identity'] for u in to_resolve}
        resolved = self.resolve_users_by_identities(identities)

        for user in to_resolve:
            identity = user['identity']
            if not (wazo_user := resolved.get(identity)):
                user['uuid'] = str(make_uuid5(tenant_uuid, identity))
                continue
            user['uuid'] = str(wazo_user.uuid)
            user.pop('identity', None)

    def list_identities(
        self,
        tenant_uuids: list[str],
        user_uuid: str | None = None,
        only_registered: bool = False,
        **filter_parameters: Any,
    ) -> list[UserIdentity]:
        identities = self._dao.user_identity.list_(
            tenant_uuids=tenant_uuids, user_uuid=user_uuid, **filter_parameters
        )
        if only_registered:
            identities = self._filter_by_registered_backends(identities)
        return identities

    def count_identities(
        self,
        tenant_uuids: list[str],
        **filter_parameters: Any,
    ) -> int:
        return self._dao.user_identity.count(
            tenant_uuids=tenant_uuids, **filter_parameters
        )

    def _filter_by_registered_backends(
        self, identities: list[UserIdentity]
    ) -> list[UserIdentity]:
        registered = self._registry.available_backends()
        return [i for i in identities if str(i.backend) in registered]

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
        self._validate_and_normalize_identity(identity)
        created = self._dao.user_identity.create(identity)
        self._notifier.created(created)
        return created

    def update_identity(self, identity: UserIdentity) -> UserIdentity:
        self._validate_and_normalize_identity(identity)
        self._dao.user_identity.update(identity)
        self._notifier.updated(identity)
        return identity

    def _validate_and_normalize_identity(self, identity: UserIdentity) -> None:
        backend_name = str(identity.backend)
        try:
            backend_cls = self._registry.get_backend(backend_name)
        except KeyError:
            raise UnknownBackendException(backend_name)

        try:
            identity.identity = backend_cls.normalize_identity(identity.identity)  # type: ignore[assignment, arg-type]
        except ValueError as e:
            raise InvalidIdentityFormatException(
                identity.identity, backend_name, str(e)  # type: ignore[arg-type]
            )

    def delete_identity(self, identity: UserIdentity) -> None:
        self._dao.user_identity.delete(identity)
        self._notifier.deleted(identity)

    def prepare_outbound_delivery(
        self,
        room: Room,
        message: RoomMessage,
        sender_identity: UserIdentity,
    ) -> None:
        backend = str(sender_identity.backend)
        sender_uuid = str(message.user_uuid)
        recipient_identities = self._resolve_outbound_recipients(
            room, sender_uuid, backend
        )
        if len(recipient_identities) != 1:
            raise UnreachableParticipantException(
                f'expected exactly 1 recipient, got {len(recipient_identities)}'
            )

        if not message.uuid:
            message.uuid = uuid4()  # type: ignore[assignment]
        message.room_uuid = room.uuid
        extra = self._build_outbound_extras(message, sender_identity, room, sender_uuid)

        self._dao.room.prepare_pending_delivery(
            message,
            recipient_identities=recipient_identities,
            sender_identity_uuid=sender_identity.uuid,  # type: ignore[arg-type]
            backend=sender_identity.backend,  # type: ignore[arg-type]
            type_=sender_identity.type_,  # type: ignore[arg-type]
            extra=extra,
        )

    @staticmethod
    def _build_outbound_extras(
        message: RoomMessage,
        sender_identity: UserIdentity,
        room: Room,
        sender_uuid: str,
    ) -> dict[str, str]:
        extra: dict[str, str] = {
            'outbound_idempotency_key': str(message.uuid) if message.uuid else '',
        }
        has_internal_recipient = any(
            str(u.uuid) != sender_uuid and not u.identity for u in room.users
        )
        if has_internal_recipient:
            extra['message_signature'] = generate_message_signature(
                str(sender_identity.identity), str(message.content or '')
            )
        return extra

    def _resolve_outbound_recipients(
        self,
        room: Room,
        sender_uuid: str,
        backend: str,
    ) -> list[str]:
        others = [u for u in room.users if str(u.uuid) != sender_uuid]
        identities = [str(u.identity) for u in others if u.identity]

        internal_uuids = [str(u.uuid) for u in others if not u.identity]
        if internal_uuids:
            resolved = self._dao.user_identity.list_identities_by_users(
                internal_uuids, backend
            )
            identities.extend(resolved[u] for u in internal_uuids if u in resolved)

        return identities

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
        # Single-recipient invariant: group rooms can't surface a sender
        # identity since dispatching to multiple recipients is not supported.
        # Drop this check when multi-recipient delivery lands.
        if len(others) != 1:
            return []

        external_identities = [str(u.identity) for u in others if u.identity]
        bound_identities = (
            self._dao.user_identity.list_bound_identities(external_identities)
            if external_identities
            else set()
        )
        db_user_ids = [
            str(u.uuid)
            for u in others
            if not u.identity or str(u.identity) in bound_identities
        ]
        db_types = (
            self._dao.user_identity.list_types_by_users(db_user_ids)
            if db_user_ids
            else {}
        )

        types_per_participant: list[set[str]] = []
        for u in others:
            identity = str(u.identity) if u.identity else None
            if identity and identity not in bound_identities:
                types_per_participant.append(
                    self._registry.resolve_reachable_types(identity)
                )
            else:
                types_per_participant.append(db_types.get(str(u.uuid), set()))

        reachable_types = set.intersection(*types_per_participant)
        if not reachable_types:
            return []

        identities = self._dao.user_identity.list_(
            user_uuid=user_uuid, types=reachable_types
        )
        return self._filter_by_registered_backends(identities)

    def validate_room_reachability(self, room: Room) -> None:
        participants = room.users
        if len(participants) < 2:
            return

        external = [u for u in participants if u.identity]
        if not external:
            return

        if len(participants) > 2:
            raise UnreachableParticipantException(
                'Group rooms with external participants are not supported'
            )

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
                    raise UnreachableParticipantException(identity)
                types_by_participant[str(user.uuid)] = reachable

        internal = [u for u in participants if not u.identity]
        needs_db_lookup.extend(internal)

        if needs_db_lookup:
            db_types = self._dao.user_identity.list_types_by_users(
                [str(u.uuid) for u in needs_db_lookup]
            )
            for user in needs_db_lookup:
                user_types = db_types.get(str(user.uuid), set())
                if not user_types:
                    raise UnreachableParticipantException(
                        str(user.identity or user.uuid)
                    )
                types_by_participant[str(user.uuid)] = user_types

        common_types: set[str] | None = None
        for types in types_by_participant.values():
            if common_types is None:
                common_types = types
            else:
                common_types &= types

        if not common_types:
            raise NoCommonConnectorException()

    def validate_identity_reachability(
        self,
        room: Room,
        user_uuid: str,
        sender_identity_uuid: UUID,
    ) -> UserIdentity:
        record = self._dao.user_identity.find(sender_identity_uuid, user_uuid=user_uuid)
        if not record:
            raise InvalidIdentityException(str(sender_identity_uuid))

        sender_backend = str(record.backend)
        sender_type = str(record.type_)
        others = [u for u in room.users if str(u.uuid) != user_uuid]

        internal = [u for u in others if not u.identity]
        external = [u for u in others if u.identity]

        if internal:
            internal_types = self._dao.user_identity.list_types_by_users(
                [str(u.uuid) for u in internal]
            )
            for user in internal:
                user_types = internal_types.get(str(user.uuid), set())
                if sender_type not in user_types:
                    raise UnreachableParticipantException(
                        str(user.uuid), sender_backend
                    )

        for user in external:
            reachable_types = self._registry.resolve_reachable_types(str(user.identity))
            if sender_type not in reachable_types:
                raise UnreachableParticipantException(
                    str(user.identity), sender_backend
                )

        return record
