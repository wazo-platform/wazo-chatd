# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import random

import pytest

from wazo_chatd.plugins.connectors.cadence import PollerCadence, apply_jitter


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestPollerCadenceColdStart:
    def test_initial_interval_is_poll_min(self) -> None:
        cadence = PollerCadence(poll_min=5.0, poll_max=60.0, clock=FakeClock())

        assert cadence.next_interval() == pytest.approx(5.0)


class TestPollerCadenceYieldStep:
    def test_yield_at_poll_min_keeps_interval_at_poll_min(self) -> None:
        clock = FakeClock()
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            tau_speedup=5.0,
            tau_slowdown=60.0,
            clock=clock,
        )

        clock.advance(5.0)
        cadence.step(did_work=True)

        assert cadence.next_interval() == pytest.approx(5.0)

    def test_yield_from_poll_max_full_dt_pulls_to_poll_min(self) -> None:
        clock = FakeClock()
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            tau_speedup=5.0,
            tau_slowdown=60.0,
            clock=clock,
        )
        cadence.interval = 60.0

        clock.advance(5.0)
        cadence.step(did_work=True)

        assert cadence.next_interval() == pytest.approx(5.0)

    def test_yield_partial_dt_partial_movement(self) -> None:
        clock = FakeClock()
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            tau_speedup=5.0,
            tau_slowdown=60.0,
            clock=clock,
        )
        cadence.interval = 60.0

        clock.advance(2.5)
        cadence.step(did_work=True)

        assert cadence.next_interval() == pytest.approx(32.5)


class TestPollerCadenceEmptyStep:
    def test_empty_full_dt_pushes_to_poll_max(self) -> None:
        clock = FakeClock()
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            tau_speedup=5.0,
            tau_slowdown=60.0,
            clock=clock,
        )

        clock.advance(60.0)
        cadence.step(did_work=False)

        assert cadence.next_interval() == pytest.approx(60.0)

    def test_empty_partial_dt_partial_decay(self) -> None:
        clock = FakeClock()
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            tau_speedup=5.0,
            tau_slowdown=60.0,
            clock=clock,
        )

        clock.advance(30.0)
        cadence.step(did_work=False)

        assert cadence.next_interval() == pytest.approx(32.5)

    def test_repeated_empty_cycles_converge_to_poll_max(self) -> None:
        clock = FakeClock()
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            tau_speedup=5.0,
            tau_slowdown=60.0,
            clock=clock,
        )

        for _ in range(50):
            clock.advance(10.0)
            cadence.step(did_work=False)

        assert cadence.next_interval() == pytest.approx(60.0, abs=0.01)


class TestPollerCadenceStability:
    def test_dt_above_tau_clamps_to_one_step(self) -> None:
        clock = FakeClock()
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            tau_speedup=5.0,
            tau_slowdown=60.0,
            clock=clock,
        )

        clock.advance(600.0)
        cadence.step(did_work=False)

        assert cadence.next_interval() == pytest.approx(60.0)

    def test_interval_bounded_below_at_poll_min(self) -> None:
        cadence = PollerCadence(poll_min=5.0, poll_max=60.0, clock=FakeClock())
        cadence.interval = 3.0

        cadence.step(did_work=True)

        assert cadence.next_interval() == pytest.approx(5.0)

    def test_interval_bounded_above_at_poll_max(self) -> None:
        cadence = PollerCadence(poll_min=5.0, poll_max=60.0, clock=FakeClock())
        cadence.interval = 100.0

        cadence.step(did_work=False)

        assert cadence.next_interval() == pytest.approx(60.0)


class TestPollerCadenceRateLimitFloor:
    def test_no_penalty_returns_poll_min_floor(self) -> None:
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            rate_limit_floor=30.0,
            clock=FakeClock(),
        )

        assert cadence.effective_min() == pytest.approx(5.0)

    def test_active_penalty_raises_floor(self) -> None:
        clock = FakeClock(start=100.0)
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            rate_limit_floor=30.0,
            clock=clock,
        )

        cadence.penalize(duration=300.0)

        assert cadence.effective_min() == pytest.approx(30.0)

    def test_expired_penalty_drops_back_to_poll_min(self) -> None:
        clock = FakeClock(start=100.0)
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            rate_limit_floor=30.0,
            clock=clock,
        )

        cadence.penalize(duration=100.0)
        clock.now = 250.0

        assert cadence.effective_min() == pytest.approx(5.0)

    def test_yield_under_penalty_pulls_to_floor_not_poll_min(self) -> None:
        clock = FakeClock(start=100.0)
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            tau_speedup=1.0,
            rate_limit_floor=30.0,
            clock=clock,
        )
        cadence.interval = 60.0
        cadence.penalize(duration=300.0)

        clock.advance(10.0)
        cadence.step(did_work=True)

        assert cadence.next_interval() == pytest.approx(30.0)

    def test_next_interval_clamps_to_floor_while_penalized(self) -> None:
        clock = FakeClock(start=100.0)
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            rate_limit_floor=30.0,
            clock=clock,
        )
        cadence.interval = 5.0

        cadence.penalize(duration=300.0)

        assert cadence.next_interval() == pytest.approx(30.0)


class TestPollerCadenceElapsedTracking:
    def test_step_uses_elapsed_since_last_step(self) -> None:
        clock = FakeClock()
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            tau_speedup=5.0,
            tau_slowdown=60.0,
            clock=clock,
        )
        cadence.interval = 60.0

        clock.advance(2.5)
        cadence.step(did_work=True)
        first = cadence.next_interval()

        clock.advance(2.5)
        cadence.step(did_work=True)
        second = cadence.next_interval()

        assert first == pytest.approx(32.5)
        assert second == pytest.approx(18.75)

    def test_penalize_does_not_consume_elapsed(self) -> None:
        clock = FakeClock()
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            tau_speedup=5.0,
            tau_slowdown=60.0,
            clock=clock,
        )

        clock.advance(60.0)
        cadence.penalize(duration=300.0)
        cadence.step(did_work=False)

        assert cadence.next_interval() == pytest.approx(60.0)


class TestApplyJitter:
    def test_zero_ratio_returns_base_value(self) -> None:
        assert apply_jitter(10.0, ratio=0.0) == pytest.approx(10.0)

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

        assert result_a == pytest.approx(result_b)
