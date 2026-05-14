# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import itertools
import random


def apply_jitter(
    value: float,
    *,
    ratio: float = 0.1,
    random_generator: random.Random | None = None,
) -> float:
    if not (0 < ratio < 1):
        return value

    if random_generator is None:
        sample = random.uniform(-ratio, ratio)
    else:
        sample = random_generator.uniform(-ratio, ratio)
    return value * (1.0 + sample)


def exponential_backoff() -> itertools.chain[int]:
    return itertools.chain([1, 2, 4, 8, 16, 32], itertools.repeat(32))


def generate_message_signature(sender_identity: str, body: str) -> str:
    """Generate a dedup signature to detect inbound echoes of outbound messages.

    Combines the sender identity with a normalized body (lowercase, ASCII-only,
    no whitespace, capped at 160 chars) and returns a truncated SHA-256 hash.
    The 160-char cap ensures consistent signatures across providers regardless
    of SMS segment reassembly behavior.
    """
    normalized = ''.join(c.lower() for c in body if c.isascii() and not c.isspace())
    payload = sender_identity + ':' + normalized[:160]

    return hashlib.sha256(payload.encode()).hexdigest()[:16]
