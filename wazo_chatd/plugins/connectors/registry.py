# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from importlib.metadata import EntryPoint

from stevedore import ExtensionManager

from wazo_chatd.plugins.connectors.connector import Connector

logger = logging.getLogger(__name__)

NAMESPACE = 'wazo_chatd.connectors'


class ConnectorRegistry:
    def __init__(self) -> None:
        self._backends: dict[str, type[Connector]] = {}
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
            self.register_backend(extension.plugin)

            mode = cfg.get('mode', 'webhook')
            verifies = getattr(extension.plugin, 'verifies_signatures', True)
            if mode == 'webhook' and not verifies:
                logger.warning(
                    'Connector backend %r: webhook mode with signature '
                    'verification off — reduced security posture.',
                    extension.name,
                )

    def register_backend(self, cls: type[Connector]) -> None:
        name = cls.backend
        if name in self._backends:
            raise ValueError(f'Connector backend {name!r} already registered')
        logger.info(
            'Registered connector backend %r (types: %s)',
            name,
            ', '.join(cls.supported_types),
        )
        self._backends[name] = cls
        self._reachable_types_cache.clear()

    def get_backend(self, name: str) -> type[Connector]:
        return self._backends[name]

    def available_backends(self) -> list[str]:
        return list(self._backends.keys())

    def types_for_backend(self, backend: str) -> set[str]:
        cls = self._backends.get(backend)
        if not cls:
            return set()
        return set(cls.supported_types)

    def backends_for_types(self, types: set[str]) -> set[str]:
        return {
            name
            for name, cls in self._backends.items()
            if types & set(cls.supported_types)
        }

    def resolve_reachable_types(self, identity: str) -> set[str]:
        if (cached := self._reachable_types_cache.get(identity)) is not None:
            return set(cached)

        reachable: set[str] = set()
        for backend_name, cls in self._backends.items():
            try:
                cls.normalize_identity(identity)
            except (ValueError, TypeError):
                continue
            reachable.update(cls.supported_types)

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
        )
