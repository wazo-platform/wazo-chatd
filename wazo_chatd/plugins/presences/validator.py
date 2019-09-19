# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from functools import wraps

from xivo.rest_api_helpers import APIException
from xivo.status import Status


class NotInitializedException(APIException):
    def __init__(self):
        msg = 'Presences are not initialized'
        super().__init__(503, msg, 'not-initialized')


class StatusValidator:
    def __init__(self):
        self._status_aggregator = None
        self._config = None

    def set_config(self, status_aggregator, config):
        self._status_aggregator = status_aggregator
        self._config = config

    def presence_initialization(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            enabled = self._config['initialization']['enabled']
            if enabled:
                status = self._status_aggregator.status()['presence_initialization'][
                    'status'
                ]
                if status != Status.ok:
                    raise NotInitializedException()
            return func(*args, **kwargs)

        return wrapper


status_validator = StatusValidator()
