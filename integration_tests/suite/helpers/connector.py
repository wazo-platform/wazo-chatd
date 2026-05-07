# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import uuid
from typing import Any

import requests


def inbound_message_payload(
    *,
    from_: str,
    to: str,
    body: str,
    message_id: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        'from': from_,
        'to': to,
        'body': body,
        'message_id': message_id or f'ext-{uuid.uuid4()}',
        **extra,
    }


def status_update_payload(
    *,
    external_id: str,
    status: str,
    **extra: Any,
) -> dict[str, Any]:
    return {'external_id': external_id, 'status': status, **extra}


class ConnectorMockClient:
    def __init__(self, host: str, port: int) -> None:
        self._base_url = f'http://{host}:{port}'

    def set_config(
        self,
        send_behavior: str = 'succeed',
        external_id: str = '',
        error_message: str = 'Test connector failure',
    ) -> None:
        requests.put(
            f'{self._base_url}/config',
            json={
                'send_behavior': send_behavior,
                'external_id': external_id,
                'error_message': error_message,
            },
        )

    def get_sent_messages(self) -> list[dict[str, str]]:
        response = requests.get(f'{self._base_url}/sent')
        return response.json()

    def set_scan(self, payload: dict[str, str]) -> None:
        requests.post(f'{self._base_url}/_set_scan', json=payload)

    def set_track(self, external_id: str, status: dict[str, str]) -> None:
        requests.post(f'{self._base_url}/_set_track/{external_id}', json=status)

    def reset(self) -> None:
        requests.post(f'{self._base_url}/reset')

    def is_up(self) -> bool:
        try:
            response = requests.get(f'{self._base_url}/config', timeout=2)
            return response.status_code == 200
        except requests.RequestException:
            return False
