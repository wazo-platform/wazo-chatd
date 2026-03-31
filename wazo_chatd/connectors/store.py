# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Iterator

from wazo_chatd.connectors.connector import Connector


class ConnectorStore:
    """Shared registry of configured connector instances.

    Written by the router (Flask thread), read by the executor
    (async delivery thread). Thread-safe for read access under the
    GIL since dict operations are atomic.
    """

    def __init__(self) -> None:
        self._instances: dict[str, Connector] = {}

    def __len__(self) -> int:
        return len(self._instances)

    def __iter__(self) -> Iterator[Connector]:
        return iter(self._instances.values())

    def register(self, name: str, connector: Connector) -> None:
        self._instances[name] = connector

    def clear(self) -> None:
        self._instances.clear()

    def find_by_backend(self, backend: str) -> Connector | None:
        for instance in self._instances.values():
            if getattr(instance, 'backend', None) == backend:
                return instance
        return None

    def backends(self) -> dict[str, str]:
        return {
            name: getattr(inst, 'backend', '?')
            for name, inst in self._instances.items()
        }
