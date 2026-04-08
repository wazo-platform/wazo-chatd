# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from sqlalchemy.orm import joinedload

from wazo_chatd.database.models import ChatProvider, UserAlias


class UserAliasDAO:
    def __init__(self, session):  # type: ignore[no-untyped-def]
        self._session = session

    @property
    def session(self):  # type: ignore[no-untyped-def]
        return self._session()

    def get(self, alias_uuid: str) -> UserAlias | None:
        return (
            self.session.query(UserAlias)
            .options(joinedload(UserAlias.provider))
            .filter(UserAlias.uuid == alias_uuid)
            .first()
        )

    def list_by_user_and_types(
        self,
        user_uuid: str,
        types: list[str] | None = None,
    ) -> list[UserAlias]:
        query = (
            self.session.query(UserAlias)
            .options(joinedload(UserAlias.provider))
            .filter(UserAlias.user_uuid == user_uuid)
        )

        if types:
            query = query.join(ChatProvider).filter(ChatProvider.type_.in_(types))

        return query.all()

    def list_types_by_user(self, user_uuid: str) -> list[str]:
        return [
            row[0]
            for row in (
                self.session.query(ChatProvider.type_)
                .join(UserAlias)
                .filter(UserAlias.user_uuid == user_uuid)
                .distinct()
                .all()
            )
        ]

    def list_types_by_users(
        self,
        user_uuids: list[str],
    ) -> dict[str, set[str]]:
        rows = (
            self.session.query(UserAlias.user_uuid, ChatProvider.type_)
            .join(ChatProvider)
            .filter(UserAlias.user_uuid.in_(user_uuids))
            .distinct()
            .all()
        )
        result: dict[str, set[str]] = {uid: set() for uid in user_uuids}
        for user_uuid, type_ in rows:
            result[str(user_uuid)].add(type_)
        return result

    def users_reachable_by_type(
        self,
        user_uuids: list[str],
        type_: str,
    ) -> set[str]:
        rows = (
            self.session.query(UserAlias.user_uuid)
            .join(ChatProvider)
            .filter(
                UserAlias.user_uuid.in_(user_uuids),
                ChatProvider.type_ == type_,
            )
            .distinct()
            .all()
        )
        return {str(row[0]) for row in rows}

    def list_bound_identities(self, identities: list[str]) -> set[str]:
        rows = (
            self.session.query(UserAlias.identity)
            .filter(UserAlias.identity.in_(identities))
            .distinct()
            .all()
        )
        return {row[0] for row in rows}

    def is_identity_bound(self, identity: str) -> bool:
        return (
            self.session.query(UserAlias).filter(UserAlias.identity == identity).first()
        ) is not None
