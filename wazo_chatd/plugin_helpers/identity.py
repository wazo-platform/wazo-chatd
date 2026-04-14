# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5


def derive_external_user_uuid(tenant_uuid: str, identity: str) -> UUID:
    return uuid5(NAMESPACE_URL, f'{tenant_uuid}:{identity}')
