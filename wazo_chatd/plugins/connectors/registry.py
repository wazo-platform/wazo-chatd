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
    """Registry of available connector backend classes.

    Populated at startup via :meth:`discover` (stevedore entry_points)
    or manually via :meth:`register_backend`.  Contains no runtime
    state — just a mapping of backend name to class.
    """

    def __init__(self) -> None:
        self._backends: dict[str, type[Connector]] = {}
        self._reachable_types_cache: dict[str, frozenset[str]] = {}

    def discover(
        self,
        connectors_config: dict[str, dict[str, str | bool]] | None = None,
    ) -> None:
        """Auto-discover installed connector backends via stevedore.

        Scans the ``wazo_chatd.connectors`` entry_point namespace for
        installed packages that provide connector backends.

        Args:
            connectors_config: If provided, only register backends that
                have ``enabled: true`` in their config entry.
        """
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
        """Register a connector backend class.

        Args:
            cls: A class implementing the :class:`Connector` protocol.

        Raises:
            ValueError: If a backend with the same ``cls.backend`` name
                is already registered.
        """
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
        """Look up a backend class by name.

        Args:
            name: The backend identifier (e.g. ``"twilio"``).

        Raises:
            KeyError: If the backend is not registered.
        """
        return self._backends[name]

    def available_backends(self) -> list[str]:
        """Return names of all registered backends."""
        return list(self._backends.keys())

    def types_for_backend(self, backend: str) -> set[str]:
        """Return supported types for a backend."""
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
        """Return connector types that can reach the given identity.

        Iterates all registered backends, calling
        ``normalize_identity()`` on each. If it succeeds, the
        backend's supported types can reach the identity. Results are
        memoized per-identity; the cache is cleared when a new backend
        registers.
        """
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
