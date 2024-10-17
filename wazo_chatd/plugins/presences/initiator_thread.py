# Copyright 2019-2024 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import itertools
import logging
import signal
import threading

import requests
from sqlalchemy.exc import SQLAlchemyError

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
        self._retry_time_failed_timeout = itertools.chain((30, 60, 120, 240, 480))

    def restart(self):
        if self._started and not self._stopped.is_set():
            logger.info('initiator thread is already running, not restarting.')
            return

        self._started = False
        self._stopped.clear()
        self.start()

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
        except requests.ReadTimeout as e:
            try:
                self._retry_time = next(self._retry_time_failed_timeout)
            except StopIteration:
                logger.error(
                    'Timeout to fetch data for initialization (%s). Stopping wazo-chatd...',
                    e,
                )
                self._stopped.set()
                signal.raise_signal(signal.SIGTERM)
                return

            logger.warning(
                'Timeout to fetch data for initialization (%s). Retrying in %s seconds...',
                e,
                self._retry_time,
            )
        except (requests.RequestException, SQLAlchemyError) as e:
            self._retry_time = next(self._retry_time_failed)
            logger.warning(
                'Error to fetch data for initialization (%s). Retrying in %s seconds...',
                e,
                self._retry_time,
            )
        else:
            self._stopped.set()
