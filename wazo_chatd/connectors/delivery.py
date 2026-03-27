# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from enum import Enum


class DeliveryStatus(str, Enum):
    """Delivery state machine states.

    Transitions::

        pending -> sending -> sent -> delivered
                     |                    |
                     v                    v
                  failed <------------- failed
                     |
                     v
                 retrying -> sending  (loop, up to MAX_RETRIES)
                     |
                     v
                dead_letter  (terminal, requires manual intervention)
    """

    PENDING = 'pending'
    SENDING = 'sending'
    SENT = 'sent'
    DELIVERED = 'delivered'
    FAILED = 'failed'
    RETRYING = 'retrying'
    DEAD_LETTER = 'dead_letter'


MAX_RETRIES: int = 3
RETRY_DELAYS: list[int] = [30, 120, 300]  # seconds: 30s, 2min, 5min
