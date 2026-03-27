# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging

from stevedore import ExtensionManager

from wazo_chatd.connectors.connector import Connector

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

    def discover(
        self,
        enabled_connectors: dict[str, bool] | None = None,
    ) -> None:
        """Auto-discover installed connector backends via stevedore.

        Scans the ``wazo_chatd.connectors`` entry_point namespace for
        installed packages that provide connector backends.

        Args:
            enabled_connectors: If provided, only register backends whose
                name is in this dict with a True value.
        """
        mgr = ExtensionManager(
            namespace=NAMESPACE,
            invoke_on_load=False,
            on_load_failure_callback=self._on_load_failure,
        )
        for ext in mgr:
            if enabled_connectors and not enabled_connectors.get(ext.name, False):
                logger.debug('Connector backend %r is disabled, skipping', ext.name)
                continue
            self.register_backend(ext.plugin)

    def register_backend(self, cls: type[Connector]) -> None:
        """Register a connector backend class.

        Args:
            cls: A class implementing the :class:`Connector` protocol.
        """
        name = cls.backend
        if name in self._backends:
            logger.warning('Connector backend %r already registered, overwriting', name)
        logger.info(
            'Registered connector backend %r (types: %s)',
            name,
            ', '.join(cls.supported_types),
        )
        self._backends[name] = cls

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

    @staticmethod
    def _on_load_failure(
        manager: ExtensionManager,
        entry_point: object,
        exception: Exception,
    ) -> None:
        logger.error(
            'Failed to load connector backend %s: %s',
            entry_point,
            exception,
        )
