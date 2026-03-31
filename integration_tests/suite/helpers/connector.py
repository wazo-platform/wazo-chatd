# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import requests


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

    def reset(self) -> None:
        requests.post(f'{self._base_url}/reset')

    def is_up(self) -> bool:
        try:
            response = requests.get(f'{self._base_url}/config', timeout=2)
            return response.status_code == 200
        except requests.RequestException:
            return False
