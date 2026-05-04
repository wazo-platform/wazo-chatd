# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class CadenceController:
    """Forward-Euler cadence controller for connector pollers."""

    poll_min: float
    poll_max: float
    tau_speedup: float = 5.0
    tau_slowdown: float = 60.0
    rate_limit_floor: float = 30.0
    interval: float = 0.0
    rate_limit_until: float = 0.0
    clock: Callable[[], float] = field(default=time.monotonic)

    def __post_init__(self) -> None:
        self.interval = self.poll_min

    def effective_min(self) -> float:
        if self.clock() < self.rate_limit_until:
            return max(self.poll_min, self.rate_limit_floor)
        return self.poll_min

    def penalize(self, *, duration: float) -> None:
        self.rate_limit_until = self.clock() + duration

    def step(self, *, yielded: bool, dt: float) -> None:
        eff_min = self.effective_min()
        target = eff_min if yielded else self.poll_max
        tau = self.tau_speedup if yielded else self.tau_slowdown
        rate = min(dt / tau, 1.0) if tau > 0 else 1.0
        self.interval += rate * (target - self.interval)
        self.interval = max(eff_min, min(self.poll_max, self.interval))

    def next_interval(self) -> float:
        return max(self.effective_min(), min(self.poll_max, self.interval))


def apply_jitter(
    value: float,
    *,
    ratio: float = 0.1,
    rng: random.Random | None = None,
) -> float:
    if ratio <= 0:
        return value
    sample = rng.uniform(-ratio, ratio) if rng else random.uniform(-ratio, ratio)
    return value * (1.0 + sample)
