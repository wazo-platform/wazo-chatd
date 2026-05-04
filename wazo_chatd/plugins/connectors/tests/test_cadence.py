# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import pytest

from wazo_chatd.plugins.connectors.cadence import CadenceController


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
