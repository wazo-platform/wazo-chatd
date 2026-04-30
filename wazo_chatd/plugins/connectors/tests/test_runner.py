# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
import concurrent.futures
import time
import unittest
import unittest.mock
from unittest.mock import AsyncMock, Mock

from wazo_chatd.plugin_helpers.dependencies import ConfigDict
from wazo_chatd.plugins.connectors.exceptions import ConnectorRateLimited
from wazo_chatd.plugins.connectors.runner import DeliveryRunner, ListenerRunner, Runner
from wazo_chatd.plugins.connectors.types import InboundMessage, StatusUpdate


def _make_config() -> ConfigDict:
    return {
        'db_uri': 'postgresql://localhost/test',
        'uuid': 'svc-uuid',
        'bus': {},
        'delivery': {'max_concurrent_tasks': 100},
    }


def _make_inbound() -> InboundMessage:
    return InboundMessage(
        sender='+15559876',
        recipient='+15551234',
        body='hello',
        backend='sms_backend',
        message_type='sms',
        external_id='ext-123',
    )


def _mock_asyncpg_conn() -> AsyncMock:
    conn = AsyncMock()
    conn.is_closed = Mock(return_value=True)
    return conn


def _mock_session_factory() -> Mock:
    result_mock = Mock()
    result_mock.all.return_value = []
    result_mock.scalars.return_value.all.return_value = []

    session = AsyncMock()
    session.execute.return_value = result_mock
    return Mock(return_value=session)


def _mock_store() -> Mock:
    """Store mock whose iteration helpers behave like an empty real store."""
    store = Mock()
    store.items.return_value = []
    store.wait_populated = AsyncMock()
    return store


class TestRunnerEntrypoint(unittest.IsolatedAsyncioTestCase):
    async def test_run_exception_propagates(self) -> None:
        class _CrashyRunner(Runner):
            async def _run(self) -> None:
                raise RuntimeError('boom')

        runner = _CrashyRunner()

        with self.assertRaises(RuntimeError):
            await runner._entrypoint()

    async def test_run_finally_runs_on_exception(self) -> None:
        cleaned = False

        class _CrashyRunner(Runner):
            async def _run(self_inner) -> None:
                nonlocal cleaned
                try:
                    raise RuntimeError('boom')
                finally:
                    cleaned = True

        runner = _CrashyRunner()

        with self.assertRaises(RuntimeError):
            await runner._entrypoint()

        assert cleaned is True

    async def test_run_cancelled_when_closing_signaled(self) -> None:
        cleaned = False

        class _IdleRunner(Runner):
            async def _run(self_inner) -> None:
                nonlocal cleaned
                self_inner.loop.call_later(
                    0.05, lambda: self_inner._closing.set_result(None)
                )
                try:
                    await self_inner._wait_closing()
                    await asyncio.sleep(10)
                finally:
                    cleaned = True

        runner = _IdleRunner()
        await runner._entrypoint()

        assert cleaned is True

    async def test_critical_task_crash_propagates(self) -> None:
        class _CrashyTaskRunner(Runner):
            async def _run(self_inner) -> None:
                task = asyncio.create_task(self_inner._crash())
                try:
                    await asyncio.wait([task])
                    if (exc := task.exception()) is not None:
                        raise exc
                finally:
                    if not task.done():
                        task.cancel()

            async def _crash(self_inner) -> None:
                raise RuntimeError('drain crashed')

        runner = _CrashyTaskRunner()

        with self.assertRaises(RuntimeError):
            await runner._entrypoint()


@unittest.mock.patch('wazo_chatd.plugins.connectors.runner.asyncpg')
@unittest.mock.patch('wazo_chatd.plugins.connectors.runner.init_async_db')
@unittest.mock.patch('wazo_chatd.plugins.connectors.runner.BusPublisher')
class TestDeliveryRunnerLifecycle(unittest.TestCase):
    def test_start_creates_loop_thread(
        self, mock_bus: Mock, mock_init_db: Mock, mock_asyncpg: Mock
    ) -> None:
        mock_init_db.return_value = (AsyncMock(), _mock_session_factory())
        mock_bus.from_config.return_value = Mock()
        mock_asyncpg.connect = AsyncMock(return_value=_mock_asyncpg_conn())

        loop = DeliveryRunner(_make_config(), Mock(), _mock_store())
        loop.start()

        try:
            assert loop._loop is not None
            assert loop._loop.is_running()
            assert loop._thread is not None
            assert loop._thread.is_alive()
        finally:
            loop.shutdown()

    def test_shutdown_stops_loop(
        self, mock_bus: Mock, mock_init_db: Mock, mock_asyncpg: Mock
    ) -> None:
        mock_init_db.return_value = (AsyncMock(), _mock_session_factory())
        mock_bus.from_config.return_value = Mock()
        mock_asyncpg.connect = AsyncMock(return_value=_mock_asyncpg_conn())

        loop = DeliveryRunner(_make_config(), Mock(), _mock_store())
        loop.start()
        loop.shutdown()

        loop._thread.join(timeout=5)
        assert not loop._thread.is_alive()

    def test_context_manager(
        self, mock_bus: Mock, mock_init_db: Mock, mock_asyncpg: Mock
    ) -> None:
        mock_init_db.return_value = (AsyncMock(), _mock_session_factory())
        mock_bus.from_config.return_value = Mock()
        mock_asyncpg.connect = AsyncMock(return_value=_mock_asyncpg_conn())

        with DeliveryRunner(_make_config(), Mock(), _mock_store()) as loop:
            assert loop._loop is not None
            assert loop._loop.is_running()

        assert loop._thread is not None
        assert not loop._thread.is_alive()


@unittest.mock.patch('wazo_chatd.plugins.connectors.runner.asyncpg')
@unittest.mock.patch('wazo_chatd.plugins.connectors.runner.init_async_db')
@unittest.mock.patch('wazo_chatd.plugins.connectors.runner.BusPublisher')
class TestDeliveryRunnerStatus(unittest.TestCase):
    def test_is_running_when_started(
        self, mock_bus: Mock, mock_init_db: Mock, mock_asyncpg: Mock
    ) -> None:
        mock_init_db.return_value = (AsyncMock(), _mock_session_factory())
        mock_bus.from_config.return_value = Mock()
        mock_asyncpg.connect = AsyncMock(return_value=_mock_asyncpg_conn())

        loop = DeliveryRunner(_make_config(), Mock(), _mock_store())
        loop.start()

        try:
            assert loop.is_running is True
        finally:
            loop.shutdown()

    def test_is_not_running_when_not_started(
        self, mock_bus: Mock, mock_init_db: Mock, mock_asyncpg: Mock
    ) -> None:
        mock_init_db.return_value = (AsyncMock(), _mock_session_factory())
        mock_bus.from_config.return_value = Mock()

        loop = DeliveryRunner(_make_config(), Mock(), _mock_store())

        assert loop.is_running is False


@unittest.mock.patch('wazo_chatd.plugins.connectors.runner.asyncpg')
@unittest.mock.patch('wazo_chatd.plugins.connectors.runner.init_async_db')
@unittest.mock.patch('wazo_chatd.plugins.connectors.runner.BusPublisher')
class TestDeliveryRunnerEnqueue(unittest.TestCase):
    def test_enqueue_inbound_creates_task(
        self, mock_bus: Mock, mock_init_db: Mock, mock_asyncpg: Mock
    ) -> None:
        mock_init_db.return_value = (AsyncMock(), _mock_session_factory())
        mock_bus.from_config.return_value = Mock()
        mock_asyncpg.connect = AsyncMock(return_value=_mock_asyncpg_conn())

        with DeliveryRunner(_make_config(), Mock(), _mock_store()) as loop:
            loop.enqueue_message(_make_inbound())
            time.sleep(0.1)

            assert loop._executor is not None


class TestDeliveryRunnerPollCycle(unittest.IsolatedAsyncioTestCase):
    @unittest.mock.patch('wazo_chatd.plugins.connectors.runner.init_async_db')
    @unittest.mock.patch('wazo_chatd.plugins.connectors.runner.BusPublisher')
    def _make_loop(
        self, mock_bus: Mock, mock_init_db: Mock, pending: list[str] | None = None
    ) -> DeliveryRunner:
        mock_init_db.return_value = (AsyncMock(), _mock_session_factory())
        mock_bus.from_config.return_value = Mock()
        config = _make_config()
        config['delivery'] = {
            **config['delivery'],
            'poll_interval_min': 1,
            'poll_interval_max': 8,
            'poll_interval_default': 2,
        }
        loop = DeliveryRunner(config, Mock(), Mock())
        loop._executor._room_dao = Mock(
            list_pending_external_ids=AsyncMock(return_value=pending or [])
        )
        loop.enqueue_message = Mock()  # type: ignore[method-assign]
        return loop

    async def test_scan_inbound_results_forwarded(self) -> None:
        loop = self._make_loop()
        message = _make_inbound()
        instance = Mock(scan_inbound=Mock(return_value=[message]))

        yielded = await loop._scan_inbound(instance, ('tenant', 'backend'))

        assert yielded is True
        loop.enqueue_message.assert_any_call(message)

    async def test_track_outbound_skipped_when_no_pending(self) -> None:
        loop = self._make_loop(pending=[])
        instance = Mock()
        instance.track_outbound = Mock(return_value=[])

        yielded = await loop._track_outbound(instance, 'tenant', 'backend')

        assert yielded is False
        instance.track_outbound.assert_not_called()

    async def test_track_outbound_called_with_pending_ids(self) -> None:
        loop = self._make_loop(pending=['ext-1', 'ext-2'])
        update = StatusUpdate(
            external_id='ext-1', status='delivered', backend='backend'
        )
        instance = Mock()
        instance.track_outbound = Mock(return_value=[update])

        yielded = await loop._track_outbound(instance, 'tenant', 'backend')

        assert yielded is True
        instance.track_outbound.assert_called_once_with(['ext-1', 'ext-2'])
        loop.enqueue_message.assert_any_call(update)

    async def test_async_scan_inbound_awaited_inline(self) -> None:
        loop = self._make_loop()
        message = _make_inbound()

        async def async_scan() -> list:
            return [message]

        instance = Mock(scan_inbound=async_scan)

        yielded = await loop._scan_inbound(instance, ('tenant', 'backend'))

        assert yielded is True
        loop.enqueue_message.assert_any_call(message)

    async def test_scan_exception_logged_returns_false(self) -> None:
        loop = self._make_loop()
        instance = Mock(scan_inbound=Mock(side_effect=RuntimeError('boom')))

        yielded = await loop._scan_inbound(instance, ('tenant', 'backend'))

        assert yielded is False
        loop.enqueue_message.assert_not_called()


class TestDeliveryRunnerPollerBackoff(unittest.IsolatedAsyncioTestCase):
    @unittest.mock.patch('wazo_chatd.plugins.connectors.runner.init_async_db')
    @unittest.mock.patch('wazo_chatd.plugins.connectors.runner.BusPublisher')
    def _make_loop(self, mock_bus: Mock, mock_init_db: Mock) -> DeliveryRunner:
        mock_init_db.return_value = (AsyncMock(), _mock_session_factory())
        mock_bus.from_config.return_value = Mock()
        config = _make_config()
        config['delivery'] = {
            **config['delivery'],
            'poll_interval_min': 1,
            'poll_interval_max': 8,
            'poll_interval_default': 2,
        }
        return DeliveryRunner(config, Mock(), Mock())

    async def test_empty_cycles_double_up_to_max(self) -> None:
        loop = self._make_loop()
        intervals: list[float] = []

        async def fake_scan(*_args: object) -> bool:
            return False

        async def fake_track(*_args: object) -> bool:
            return False

        loop._scan_inbound = fake_scan  # type: ignore[method-assign,assignment]
        loop._track_outbound = fake_track  # type: ignore[method-assign,assignment]

        async def capture_sleep(d: float) -> None:
            intervals.append(d)
            if len(intervals) >= 5:
                raise asyncio.CancelledError()

        with unittest.mock.patch(
            'wazo_chatd.plugins.connectors.runner.asyncio.sleep', capture_sleep
        ):
            with self.assertRaises(asyncio.CancelledError):
                await loop._run_poller(('tenant', 'backend'), Mock())

        assert intervals == [4, 8, 8, 8, 8]

    async def test_non_empty_cycle_snaps_to_min(self) -> None:
        loop = self._make_loop()
        intervals: list[float] = []
        call_count = {'n': 0}

        async def fake_scan(*_args: object) -> bool:
            call_count['n'] += 1
            return call_count['n'] == 3

        async def fake_track(*_args: object) -> bool:
            return False

        loop._scan_inbound = fake_scan  # type: ignore[method-assign,assignment]
        loop._track_outbound = fake_track  # type: ignore[method-assign,assignment]

        async def capture_sleep(d: float) -> None:
            intervals.append(d)
            if len(intervals) >= 4:
                raise asyncio.CancelledError()

        with unittest.mock.patch(
            'wazo_chatd.plugins.connectors.runner.asyncio.sleep', capture_sleep
        ):
            with self.assertRaises(asyncio.CancelledError):
                await loop._run_poller(('tenant', 'backend'), Mock())

        assert intervals[0] == 4
        assert intervals[1] == 8
        assert intervals[2] == 1
        assert intervals[3] == 2

    async def test_rate_limited_uses_provider_retry_after(self) -> None:
        loop = self._make_loop()
        intervals: list[float] = []

        async def fake_scan(*_args: object) -> bool:
            raise ConnectorRateLimited('rate limited', retry_after=42.0)

        async def fake_track(*_args: object) -> bool:
            return False

        loop._scan_inbound = fake_scan  # type: ignore[method-assign,assignment]
        loop._track_outbound = fake_track  # type: ignore[method-assign,assignment]

        async def capture_sleep(d: float) -> None:
            intervals.append(d)
            raise asyncio.CancelledError()

        with unittest.mock.patch(
            'wazo_chatd.plugins.connectors.runner.asyncio.sleep', capture_sleep
        ):
            with self.assertRaises(asyncio.CancelledError):
                await loop._run_poller(('tenant', 'backend'), Mock())

        assert intervals == [42.0]

    async def test_rate_limited_caps_retry_after_at_max(self) -> None:
        loop = self._make_loop()
        intervals: list[float] = []

        async def fake_scan(*_args: object) -> bool:
            raise ConnectorRateLimited('rate limited', retry_after=999_999.0)

        async def fake_track(*_args: object) -> bool:
            return False

        loop._scan_inbound = fake_scan  # type: ignore[method-assign,assignment]
        loop._track_outbound = fake_track  # type: ignore[method-assign,assignment]

        async def capture_sleep(d: float) -> None:
            intervals.append(d)
            raise asyncio.CancelledError()

        with unittest.mock.patch(
            'wazo_chatd.plugins.connectors.runner.asyncio.sleep', capture_sleep
        ):
            with self.assertRaises(asyncio.CancelledError):
                await loop._run_poller(('tenant', 'backend'), Mock())

        assert intervals == [3600.0]


def _build_loop_for_modes(connectors_config: dict) -> DeliveryRunner:
    with unittest.mock.patch(
        'wazo_chatd.plugins.connectors.runner.init_async_db',
        return_value=(AsyncMock(), _mock_session_factory()),
    ), unittest.mock.patch(
        'wazo_chatd.plugins.connectors.runner.BusPublisher'
    ) as mock_bus:
        mock_bus.from_config.return_value = Mock()
        config = _make_config()
        config['connectors'] = connectors_config
        store = Mock()
        store.items.return_value = []
        loop = DeliveryRunner(config, Mock(), store)
        loop._loop = asyncio.get_event_loop()
        return loop


def _mock_instance(backend: str) -> Mock:
    instance = Mock()
    instance.backend = backend
    return instance


class TestListenerRunnerReconcile(unittest.IsolatedAsyncioTestCase):
    def _make_runner(self) -> ListenerRunner:
        runner = ListenerRunner(_make_config(), Mock(), Mock())
        runner._loop = asyncio.get_event_loop()
        return runner

    async def test_spawns_listener_for_new_instance(self) -> None:
        runner = self._make_runner()
        instance = _mock_instance('push')

        async def fake_listen(on_message: object) -> None:
            await asyncio.sleep(3600)

        instance.listen = fake_listen
        key = ('tenant-a', 'push')

        runner._reconcile({key: instance})

        assert key in runner._listeners
        assert not runner._listeners[key].done()
        runner._listeners[key].cancel()

    async def test_empty_desired_does_nothing(self) -> None:
        runner = self._make_runner()

        runner._reconcile({})

        assert runner._listeners == {}

    async def test_cancels_listener_for_removed_instance(self) -> None:
        runner = self._make_runner()
        instance = _mock_instance('push')

        async def fake_listen(on_message: object) -> None:
            await asyncio.sleep(3600)

        instance.listen = fake_listen
        key = ('tenant-a', 'push')

        runner._reconcile({key: instance})
        task = runner._listeners[key]

        runner._reconcile({})

        assert key not in runner._listeners
        assert task.cancelling() > 0 or task.done()
        assert task.cancelling() > 0 or task.done()


class TestDeliveryRunnerSynchronizePollers(unittest.IsolatedAsyncioTestCase):
    async def test_spawns_poller_for_poll_mode_instance(self) -> None:
        loop = _build_loop_for_modes({'sms_backend': {'mode': 'poll'}})
        key = ('tenant-a', 'sms_backend')
        loop._store.items.return_value = [(key, _mock_instance('sms_backend'))]

        loop._synchronize_pollers()

        assert key in loop._pollers
        assert not loop._pollers[key].done()
        loop._pollers[key].cancel()

    async def test_does_not_spawn_poller_for_webhook_mode(self) -> None:
        loop = _build_loop_for_modes({'sms_backend': {'mode': 'webhook'}})
        key = ('tenant-a', 'sms_backend')
        loop._store.items.return_value = [(key, _mock_instance('sms_backend'))]

        loop._synchronize_pollers()

        assert key not in loop._pollers

    async def test_idempotent_does_not_spawn_duplicate(self) -> None:
        loop = _build_loop_for_modes({'sms_backend': {'mode': 'poll'}})
        key = ('tenant-a', 'sms_backend')
        loop._store.items.return_value = [(key, _mock_instance('sms_backend'))]

        loop._synchronize_pollers()
        first_task = loop._pollers[key]

        loop._synchronize_pollers()

        assert loop._pollers[key] is first_task
        first_task.cancel()

    async def test_cancels_poller_for_evicted_instance(self) -> None:
        loop = _build_loop_for_modes({'sms_backend': {'mode': 'poll'}})
        key = ('tenant-a', 'sms_backend')
        loop._store.items.return_value = [(key, _mock_instance('sms_backend'))]

        loop._synchronize_pollers()
        task = loop._pollers[key]

        loop._store.items.return_value = []
        loop._synchronize_pollers()

        assert key not in loop._pollers
        assert task.cancelling() > 0


class TestDeliveryRunnerWaitBackoff(unittest.TestCase):
    @unittest.mock.patch('wazo_chatd.plugins.connectors.runner.init_async_db')
    @unittest.mock.patch('wazo_chatd.plugins.connectors.runner.BusPublisher')
    def _make_runner(self, mock_bus: Mock, mock_init_db: Mock) -> DeliveryRunner:
        mock_init_db.return_value = (AsyncMock(), _mock_session_factory())
        mock_bus.from_config.return_value = Mock()
        runner = DeliveryRunner(_make_config(), Mock(), Mock())
        runner._closing = Mock()
        runner._closing.done.return_value = False
        return runner

    def _simulate_timeout(self, runner: DeliveryRunner) -> list[float]:
        delays: list[float] = []

        def capture(timeout: float) -> None:
            delays.append(timeout)
            raise concurrent.futures.TimeoutError()

        runner._closing.result.side_effect = capture  # type: ignore[attr-defined]
        return delays

    def test_increments_count(self) -> None:
        runner = self._make_runner()
        self._simulate_timeout(runner)

        assert runner._wait_backoff() is True
        assert runner.restart_count == 1
        assert runner._wait_backoff() is True
        assert runner.restart_count == 2

    def test_delays_increase(self) -> None:
        runner = self._make_runner()
        delays = self._simulate_timeout(runner)

        for _ in range(4):
            runner._wait_backoff()

        assert delays == [1, 2, 4, 8]

    def test_resets_when_healthy(self) -> None:
        runner = self._make_runner()
        delays = self._simulate_timeout(runner)

        runner._wait_backoff()
        runner._wait_backoff()
        assert delays == [1, 2]

        runner._healthy.set()
        runner._wait_backoff()
        assert delays[-1] == 1

    def test_returns_false_when_closing_signaled(self) -> None:
        runner = self._make_runner()
        runner._closing.result.return_value = None  # type: ignore[attr-defined]

        assert runner._wait_backoff() is False
