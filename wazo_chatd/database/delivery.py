# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from enum import Enum


class DeliveryStatus(str, Enum):
    """Delivery lifecycle states.

    Executor writes (after :meth:`Connector.send` returns):
        ``PENDING`` (created, not yet picked up) →
        ``ACCEPTED`` (provider's API accepted submission) on success, or
        ``FAILED`` → ``RETRYING`` / ``DEAD_LETTER`` on error.

    Provider writes (via webhook or :meth:`Connector.track_outbound`,
    mapped through :attr:`Connector.status_map`):
        ``ACCEPTED`` → ``SENT`` (provider sent to carrier) →
        ``DELIVERED`` (recipient confirmed), or ``FAILED`` at any step.
    """

    PENDING = 'pending'
    ACCEPTED = 'accepted'
    SENT = 'sent'
    DELIVERED = 'delivered'
    FAILED = 'failed'
    RETRYING = 'retrying'
    DEAD_LETTER = 'dead_letter'
