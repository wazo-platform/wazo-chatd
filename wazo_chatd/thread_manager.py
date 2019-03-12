# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

logger = logging.getLogger(__name__)


class ThreadManager(object):

    def __init__(self):
        self._threads_wrapper = []

    def manage(self, thread_wrapper):
        self._threads_wrapper.append(thread_wrapper)

    def start(self):
        for thread_wrapper in self._threads_wrapper:
            thread_wrapper.start()

    def stop(self):
        for thread_wrapper in self._threads_wrapper:
            thread_wrapper.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()
