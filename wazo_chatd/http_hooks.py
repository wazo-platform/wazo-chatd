# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from collections.abc import Callable

from flask import g, has_app_context

logger = logging.getLogger(__name__)


def register_post_commit_callback(callback: Callable[[], None]) -> None:
    """Register a callback to run after the next successful database commit.

    Callbacks are stored on Flask's ``g`` object and executed during
    ``teardown_appcontext``, after the database commit succeeds.
    Ignored if called outside an application context.

    Args:
        callback: A no-argument callable.
    """
    if not has_app_context():
        logger.warning(
            'register_post_commit_callback called outside app context, ignoring'
        )
        return

    callbacks = getattr(g, '_post_commit_callbacks', None)
    if callbacks is None:
        callbacks = []
        g._post_commit_callbacks = callbacks
    callbacks.append(callback)


def run_post_commit_callbacks() -> None:
    """Execute all registered post-commit callbacks.

    Called by ``teardown_appcontext`` after a successful commit.
    Each callback runs independently — a failure in one does not
    prevent the others from executing.
    """
    for callback in getattr(g, '_post_commit_callbacks', []):
        try:
            callback()
        except Exception:
            logger.exception('Post-commit callback failed')
