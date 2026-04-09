# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from enum import Enum


class DeliveryStatus(str, Enum):
    PENDING = 'pending'
    SENDING = 'sending'
    SENT = 'sent'
    DELIVERED = 'delivered'
    FAILED = 'failed'
    RETRYING = 'retrying'
    DEAD_LETTER = 'dead_letter'
