# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CadenceController:
    """Forward-Euler cadence controller for connector pollers."""

    poll_min: float
    poll_max: float
    tau_speedup: float = 5.0
    tau_slowdown: float = 60.0
    interval: float = 0.0

    def __post_init__(self) -> None:
        self.interval = self.poll_min

    def step(self, *, yielded: bool, dt: float) -> None:
        target = self.poll_min if yielded else self.poll_max
        tau = self.tau_speedup if yielded else self.tau_slowdown
        rate = min(dt / tau, 1.0) if tau > 0 else 1.0
        self.interval += rate * (target - self.interval)
        self.interval = max(self.poll_min, min(self.poll_max, self.interval))

    def next_interval(self) -> float:
        return self.interval
