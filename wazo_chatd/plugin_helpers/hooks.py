# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class Hooks:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[..., None]]] = defaultdict(list)

    def register(self, name: str, callback: Callable[..., None]) -> None:
        self._subscribers[name].append(callback)

    def has_subscribers(self, name: str) -> bool:
        return name in self._subscribers

    def dispatch(self, name: str, *args: Any, allow_raise: bool = False) -> None:
        for callback in self._subscribers.get(name, []):
            try:
                callback(*args)
            except Exception as e:
                logger.warning(
                    'Hook subscriber %s failed: %s',
                    callback,
                    e,
                    exc_info=not allow_raise,
                )
                if allow_raise:
                    raise
