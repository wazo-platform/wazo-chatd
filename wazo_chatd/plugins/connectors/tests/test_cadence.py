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


class TestPollerCadenceStep:
    @pytest.mark.parametrize(
        ('initial', 'did_work', 'dt', 'expected'),
        [
            pytest.param(5.0, True, 5.0, 5.0, id='yield_at_poll_min_stays'),
            pytest.param(60.0, True, 5.0, 5.0, id='yield_full_dt_pulls_to_poll_min'),
            pytest.param(60.0, True, 2.5, 32.5, id='yield_partial_dt_partial_movement'),
            pytest.param(5.0, False, 60.0, 60.0, id='empty_full_dt_pushes_to_poll_max'),
            pytest.param(5.0, False, 30.0, 32.5, id='empty_partial_dt_partial_decay'),
            pytest.param(5.0, False, 600.0, 60.0, id='empty_dt_above_tau_clamps'),
        ],
    )
    def test_step_moves_interval(
        self,
        initial: float,
        did_work: bool,
        dt: float,
        expected: float,
    ) -> None:
        clock = FakeClock()
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            tau_speedup=5.0,
            tau_slowdown=60.0,
            clock=clock,
        )
        cadence.interval = initial

        clock.advance(dt)
        cadence.step(did_work=did_work)

        assert cadence.next_interval() == pytest.approx(expected)

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


class TestPollerCadenceBounds:
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
    @pytest.mark.parametrize(
        ('penalty_duration', 'time_after_penalty', 'expected'),
        [
            pytest.param(None, 0.0, 5.0, id='no_penalty'),
            pytest.param(300.0, 0.0, 30.0, id='active_penalty'),
            pytest.param(100.0, 150.0, 5.0, id='expired_penalty'),
        ],
    )
    def test_effective_min(
        self,
        penalty_duration: float | None,
        time_after_penalty: float,
        expected: float,
    ) -> None:
        clock = FakeClock(start=100.0)
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            rate_limit_floor=30.0,
            clock=clock,
        )
        if penalty_duration is not None:
            cadence.penalize(duration=penalty_duration)
        clock.advance(time_after_penalty)

        assert cadence.effective_min() == pytest.approx(expected)

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

    def test_reset_step_clock_discards_elapsed_time(self) -> None:
        clock = FakeClock()
        cadence = PollerCadence(
            poll_min=5.0,
            poll_max=60.0,
            tau_speedup=5.0,
            tau_slowdown=60.0,
            clock=clock,
        )
        cadence.interval = 60.0

        clock.advance(60.0)
        cadence.reset_step_clock()

        clock.advance(2.5)
        cadence.step(did_work=True)

        assert cadence.next_interval() == pytest.approx(32.5)


class TestApplyJitter:
    @pytest.mark.parametrize('ratio', [-0.1, 0.0, 1.0, 1.5])
    def test_out_of_range_ratio_returns_base_value(self, ratio: float) -> None:
        assert apply_jitter(10.0, ratio=ratio) == pytest.approx(10.0)

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
