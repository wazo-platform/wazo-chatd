# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Worker process supervisor.

Runs in the main chatd process. Monitors the message worker process
and restarts it with exponential backoff if it dies. Reports worker
health on the ``/status`` endpoint.
"""

from __future__ import annotations

import logging
import time
from threading import Thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wazo_chatd.connectors.router import ConnectorRouter

from typing import Protocol as TypingProtocol

logger = logging.getLogger(__name__)

_MAX_RESTART_DELAY: int = 60
_HEALTH_CHECK_INTERVAL: float = 5.0
_PING_TIMEOUT: float = 3.0


class _WorkerServer(TypingProtocol):
    """Minimal interface the supervisor needs from the server process."""

    @property
    def process(self) -> _WorkerProcess:
        ...  # noqa: E704

    def serve_forever(self) -> None:
        ...  # noqa: E704

    def shutdown(self, timeout: float = 10) -> None:
        ...  # noqa: E704

    def ping(self, timeout: float = 5) -> bool:
        ...  # noqa: E704


class _WorkerProcess(TypingProtocol):
    """Minimal interface for the underlying process handle."""

    def is_alive(self) -> bool:
        ...  # noqa: E704

    def join(self, timeout: float | None = None) -> None:
        ...  # noqa: E704

    @property
    def exitcode(self) -> int | None:
        ...  # noqa: E704


class WorkerSupervisor:
    """Monitors and supervises the message worker process."""

    def __init__(self, server: _WorkerServer, router: ConnectorRouter) -> None:
        self._server = server
        self._router = router
        self._stopped = False
        self._restart_count = 0
        self._watchdog: Thread | None = None

    @property
    def restart_count(self) -> int:
        return self._restart_count

    def start(self) -> None:
        """Start the worker process and the watchdog thread."""
        self._server.serve_forever()
        self._watchdog = Thread(
            target=self._watch,
            name='connector-worker-watchdog',
            daemon=True,
        )
        self._watchdog.start()

    def shutdown(self, timeout: float = 10) -> None:
        """Gracefully stop the worker process."""
        self._stopped = True
        self._server.shutdown(timeout=timeout)

    def provide_status(self, status: dict[str, dict[str, str | int]]) -> None:
        """Report worker health for the ``/status`` endpoint.

        Registered with ``status_aggregator.add_provider()``.
        """
        is_alive = self._server.process.is_alive()
        is_responsive = is_alive and self._server.ping(timeout=2)
        status['message_worker'] = {
            'status': 'ok' if is_responsive else 'fail',
            'restart_count': self._restart_count,
        }

    def _watch(self) -> None:
        while not self._stopped:
            time.sleep(_HEALTH_CHECK_INTERVAL)
            if self._stopped:
                break

            if not self._server.process.is_alive():
                logger.error(
                    'Worker process died (exit code %s), restarting...',
                    self._server.process.exitcode,
                )
                self._restart_with_backoff()
                continue

            if not self._server.ping(timeout=_PING_TIMEOUT):
                logger.error(
                    'Worker process unresponsive (ping timeout), restarting...'
                )
                self._server.shutdown(timeout=5)
                self._restart_with_backoff()

    def _restart_with_backoff(self) -> None:
        delay = min(2**self._restart_count, _MAX_RESTART_DELAY)
        logger.info(
            'Restarting worker in %ds (attempt #%d)',
            delay,
            self._restart_count + 1,
        )
        time.sleep(delay)

        self._server.serve_forever()
        self._router.sync_to_server()
        self._restart_count += 1
