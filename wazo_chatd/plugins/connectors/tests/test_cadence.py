# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import random

import pytest

from wazo_chatd.plugins.connectors.cadence import CadenceController, apply_jitter


class TestCadenceControllerColdStart:
    def test_initial_interval_is_poll_min(self) -> None:
        controller = CadenceController(poll_min=5.0, poll_max=60.0)

        assert controller.next_interval() == 5.0


class TestCadenceControllerYieldStep:
    def test_yield_at_poll_min_keeps_interval_at_poll_min(self) -> None:
        controller = CadenceController(
            poll_min=5.0, poll_max=60.0, tau_speedup=5.0, tau_slowdown=60.0
        )

        controller.step(yielded=True, dt=5.0)

        assert controller.next_interval() == pytest.approx(5.0)

    def test_yield_from_poll_max_full_dt_pulls_to_poll_min(self) -> None:
        controller = CadenceController(
            poll_min=5.0, poll_max=60.0, tau_speedup=5.0, tau_slowdown=60.0
        )
        controller.interval = 60.0

        controller.step(yielded=True, dt=5.0)

        assert controller.next_interval() == pytest.approx(5.0)

    def test_yield_partial_dt_partial_movement(self) -> None:
        controller = CadenceController(
            poll_min=5.0, poll_max=60.0, tau_speedup=5.0, tau_slowdown=60.0
        )
        controller.interval = 60.0

        controller.step(yielded=True, dt=2.5)

        assert controller.next_interval() == pytest.approx(32.5)


class TestCadenceControllerEmptyStep:
    def test_empty_full_dt_pushes_to_poll_max(self) -> None:
        controller = CadenceController(
            poll_min=5.0, poll_max=60.0, tau_speedup=5.0, tau_slowdown=60.0
        )

        controller.step(yielded=False, dt=60.0)

        assert controller.next_interval() == pytest.approx(60.0)

    def test_empty_partial_dt_partial_decay(self) -> None:
        controller = CadenceController(
            poll_min=5.0, poll_max=60.0, tau_speedup=5.0, tau_slowdown=60.0
        )

        controller.step(yielded=False, dt=30.0)

        assert controller.next_interval() == pytest.approx(32.5)

    def test_repeated_empty_cycles_converge_to_poll_max(self) -> None:
        controller = CadenceController(
            poll_min=5.0, poll_max=60.0, tau_speedup=5.0, tau_slowdown=60.0
        )

        for _ in range(50):
            controller.step(yielded=False, dt=10.0)

        assert controller.next_interval() == pytest.approx(60.0, abs=0.01)


class TestCadenceControllerStability:
    def test_dt_above_tau_clamps_to_one_step(self) -> None:
        controller = CadenceController(
            poll_min=5.0, poll_max=60.0, tau_speedup=5.0, tau_slowdown=60.0
        )

        controller.step(yielded=False, dt=600.0)

        assert controller.next_interval() == pytest.approx(60.0)

    def test_interval_bounded_below_at_poll_min(self) -> None:
        controller = CadenceController(poll_min=5.0, poll_max=60.0)
        controller.interval = 3.0

        controller.step(yielded=True, dt=0.0)

        assert controller.next_interval() == 5.0

    def test_interval_bounded_above_at_poll_max(self) -> None:
        controller = CadenceController(poll_min=5.0, poll_max=60.0)
        controller.interval = 100.0

        controller.step(yielded=False, dt=0.0)

        assert controller.next_interval() == 60.0


class TestCadenceControllerRateLimitFloor:
    def test_no_penalty_returns_poll_min_floor(self) -> None:
        controller = CadenceController(
            poll_min=5.0,
            poll_max=60.0,
            rate_limit_floor=30.0,
        )

        assert controller.effective_min() == 5.0

    def test_active_penalty_raises_floor(self) -> None:
        now = [100.0]
        controller = CadenceController(
            poll_min=5.0,
            poll_max=60.0,
            rate_limit_floor=30.0,
            clock=lambda: now[0],
        )

        controller.penalize(duration=300.0)

        assert controller.effective_min() == 30.0

    def test_expired_penalty_drops_back_to_poll_min(self) -> None:
        now = [100.0]
        controller = CadenceController(
            poll_min=5.0,
            poll_max=60.0,
            rate_limit_floor=30.0,
            clock=lambda: now[0],
        )

        controller.penalize(duration=100.0)
        now[0] = 250.0

        assert controller.effective_min() == 5.0

    def test_yield_under_penalty_pulls_to_floor_not_poll_min(self) -> None:
        now = [100.0]
        controller = CadenceController(
            poll_min=5.0,
            poll_max=60.0,
            tau_speedup=1.0,
            rate_limit_floor=30.0,
            clock=lambda: now[0],
        )
        controller.interval = 60.0
        controller.penalize(duration=300.0)

        controller.step(yielded=True, dt=10.0)

        assert controller.next_interval() == pytest.approx(30.0)

    def test_next_interval_clamps_to_floor_while_penalized(self) -> None:
        now = [100.0]
        controller = CadenceController(
            poll_min=5.0,
            poll_max=60.0,
            rate_limit_floor=30.0,
            clock=lambda: now[0],
        )
        controller.interval = 5.0

        controller.penalize(duration=300.0)

        assert controller.next_interval() == 30.0


class TestApplyJitter:
    def test_zero_ratio_returns_base_value(self) -> None:
        assert apply_jitter(10.0, ratio=0.0) == 10.0

    def test_jittered_value_stays_within_ratio(self) -> None:
        rng = random.Random(42)

        for _ in range(100):
            result = apply_jitter(10.0, ratio=0.1, rng=rng)
            assert 9.0 <= result <= 11.0

    def test_seeded_rng_is_deterministic(self) -> None:
        rng_a = random.Random(42)
        rng_b = random.Random(42)

        result_a = apply_jitter(10.0, ratio=0.1, rng=rng_a)
        result_b = apply_jitter(10.0, ratio=0.1, rng=rng_b)

        assert result_a == result_b
