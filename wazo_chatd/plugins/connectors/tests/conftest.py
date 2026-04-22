# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared fixtures for the connectors plugin unit tests."""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def fail_on_thread_exception() -> Iterator[None]:
    """Promote uncaught thread exceptions to test failures instead of warnings."""
    captured: list[threading.ExceptHookArgs] = []
    original = threading.excepthook

    def capture(args: threading.ExceptHookArgs) -> None:
        captured.append(args)
        original(args)

    threading.excepthook = capture
    try:
        yield
    finally:
        threading.excepthook = original

    if captured:
        args = captured[0]
        thread_name = args.thread.name if args.thread is not None else '<unknown>'
        raise AssertionError(
            f'Unhandled exception in thread {thread_name!r}: '
            f'{args.exc_type.__name__}: {args.exc_value}'
        ) from args.exc_value
