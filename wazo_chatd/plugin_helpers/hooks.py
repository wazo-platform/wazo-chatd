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

    def dispatch(self, name: str, payload: Any, *, propagate_errors: bool = False) -> None:
        for callback in self._subscribers[name]:
            if propagate_errors:
                callback(payload)
            else:
                try:
                    callback(payload)
                except Exception:
                    logger.exception('Hook subscriber %s failed', callback)
