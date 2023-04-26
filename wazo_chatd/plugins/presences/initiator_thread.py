# Copyright 2019-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import itertools
import logging
import threading

from sqlalchemy.exc import SQLAlchemyError
import requests

logger = logging.getLogger(__name__)


class InitiatorThread:
    def __init__(self, initiator):
        self._initiator = initiator
        self._started = False
        self._stopped = threading.Event()
        self._retry_time = 0
        self._retry_time_failed = itertools.chain(
            (1, 2, 4, 8, 16), itertools.repeat(32)
        )

    def start(self):
        if self._started:
            raise Exception('Initialization already started')

        self._started = True
        thread_name = 'presence_initialization'
        self._thread = threading.Thread(target=self._run, name=thread_name)
        self._thread.start()

    def stop(self):
        self._stopped.set()
        logger.debug('joining presence initialization thread...')
        self._thread.join()

    def _run(self):
        self._initiate()
        while True:
            self._stopped.wait(self._retry_time)
            if self._stopped.is_set():
                return

            self._initiate()

    def _initiate(self):
        logger.debug('Starting presence initialization')
        try:
            self._initiator.initiate()
        except (requests.RequestException, SQLAlchemyError) as e:
            self._retry_time = next(self._retry_time_failed)
            logger.warning(
                'Error to fetch data for initialization (%s). Retrying in %s seconds...',
                e,
                self._retry_time,
            )
        else:
            self._stopped.set()
