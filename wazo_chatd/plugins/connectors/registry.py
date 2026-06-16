# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.metadata import EntryPoint
from typing import cast, get_args

from stevedore import ExtensionManager

from wazo_chatd.plugins.connectors.connector import Connector
from wazo_chatd.plugins.connectors.helpers import VALID_TRANSPORT_MODES
from wazo_chatd.plugins.connectors.schemas import connector_auth_schema
from wazo_chatd.plugins.connectors.types import AuthScope, ConfigField, TransportMode

logger = logging.getLogger(__name__)

NAMESPACE = 'wazo_chatd.connectors'
_VALID_AUTH_SCOPES = get_args(AuthScope)


@dataclass(frozen=True)
class _RegisteredBackend:
    cls: type[Connector]
    auth_schema: tuple[str, str]
    mode: TransportMode


class ConnectorRegistry:
    def __init__(self) -> None:
        self._backends: dict[str, _RegisteredBackend] = {}
        self._reachable_types_cache: dict[str, frozenset[str]] = {}

    def discover(
        self,
        connectors_config: dict[str, dict[str, str | bool]] | None = None,
    ) -> None:
        connectors_config = connectors_config or {}
        manager = ExtensionManager(
            namespace=NAMESPACE,
            invoke_on_load=False,
            on_load_failure_callback=self._on_load_failure,
        )
        for extension in manager:
            cfg = connectors_config.get(extension.name, {}) or {}
            if not cfg.get('enabled', False):
                logger.debug(
                    'Connector backend %r is disabled, skipping', extension.name
                )
                continue

            if (mode := cfg.get('mode') or 'webhook') not in VALID_TRANSPORT_MODES:
                logger.error(
                    'Connector backend %r: invalid mode %r (expected one of %s); '
                    'not loading',
                    extension.name,
                    mode,
                    list(VALID_TRANSPORT_MODES),
                )
                continue

            self.register_backend(extension.plugin, mode=cast(TransportMode, mode))

            verifies = getattr(extension.plugin, 'verifies_signatures', True)
            if mode == 'webhook' and not verifies:
                logger.warning(
                    'Connector backend %r: webhook mode with signature '
                    'verification off — reduced security posture.',
                    extension.name,
                )

    def register_backend(
        self, cls: type[Connector], mode: TransportMode = 'webhook'
    ) -> None:
        name = cls.backend
        if name in self._backends:
            raise ValueError(f'Connector backend {name!r} already registered')

        auth_scope = getattr(cls, 'auth_scope', 'tenant')
        auth_schema = tuple(getattr(cls, 'auth_schema', ()))
        _validate_auth_schema(name, auth_scope, auth_schema)

        payload, etag = _serialize_schema(auth_scope, auth_schema)

        logger.info(
            'Registered connector backend %r (types: %s)',
            name,
            ', '.join(cls.supported_types),
        )
        self._backends[name] = _RegisteredBackend(cls, (payload, etag), mode)
        self._reachable_types_cache.clear()

    def transport_mode(self, name: str) -> TransportMode:
        return self._backends[name].mode

    def get_auth_schema(self, name: str) -> tuple[str, str]:
        return self._backends[name].auth_schema

    def get_backend(self, name: str) -> type[Connector]:
        return self._backends[name].cls

    def requires_auth(self, name: str) -> bool:
        return getattr(self._backends[name].cls, 'auth_scope', 'tenant') != 'none'

    def available_backends(self) -> list[str]:
        return list(self._backends.keys())

    def types_for_backend(self, backend: str) -> set[str]:
        entry = self._backends.get(backend)
        if not entry:
            return set()
        return set(entry.cls.supported_types)

    def backends_for_types(self, types: set[str]) -> set[str]:
        return {
            name
            for name, entry in self._backends.items()
            if types & set(entry.cls.supported_types)
        }

    def resolve_reachable_types(self, identity: str) -> set[str]:
        if (cached := self._reachable_types_cache.get(identity)) is not None:
            return set(cached)

        reachable: set[str] = set()
        for entry in self._backends.values():
            try:
                entry.cls.normalize_identity(identity)
            except (ValueError, TypeError):
                continue
            reachable.update(entry.cls.supported_types)

        self._reachable_types_cache[identity] = frozenset(reachable)
        return reachable

    @staticmethod
    def _on_load_failure(
        manager: ExtensionManager,
        entry_point: EntryPoint,
        exception: Exception,
    ) -> None:
        logger.error(
            'Failed to load connector backend %s: %s',
            entry_point,
            exception,
            exc_info=exception,
        )


def _validate_auth_schema(
    backend: str, scope: str, schema: tuple[ConfigField, ...]
) -> None:
    if scope not in _VALID_AUTH_SCOPES:
        raise ValueError(
            f'Connector {backend!r}: invalid auth_scope {scope!r}, '
            f'expected one of {_VALID_AUTH_SCOPES}'
        )

    if scope == 'none' and schema:
        raise ValueError(
            f"Connector {backend!r}: auth_scope='none' must declare no fields"
        )

    seen: set[str] = set()
    for cfield in schema:
        if cfield.name in seen:
            raise ValueError(
                f'Connector {backend!r}: duplicate field name {cfield.name!r}'
            )
        seen.add(cfield.name)


def _serialize_schema(scope: str, fields: Sequence[ConfigField]) -> tuple[str, str]:
    body = connector_auth_schema.dump({'scope': scope, 'fields': list(fields)})
    payload = json.dumps(body, sort_keys=True, separators=(',', ':'))
    etag = hashlib.sha256(payload.encode()).hexdigest()
    return payload, etag
