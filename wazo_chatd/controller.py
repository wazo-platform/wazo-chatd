# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0+

import logging
import signal

from functools import partial
from xivo import plugin_helpers
from .http_server import api, CoreRestApi

logger = logging.getLogger(__name__)


class Controller:

    def __init__(self, config):
        self.rest_api = CoreRestApi(config)
        plugin_helpers.load(
            namespace='wazo_chatd.plugins',
            names=config['enabled_plugins'],
            dependencies={
                'api': api,
            }
        )

    def run(self):
        logger.info('wazo-chatd starting...')
        signal.signal(signal.SIGTERM, partial(_sigterm_handler, self))
        try:
            self.rest_api.run()

        finally:
            logger.info('wazo-chatd stopping...')

    def stop(self, reason):
        logger.warning('Stopping wazo-chatd: %s', reason)
        self.rest_api.stop()


def _sigterm_handler(controller, signum, frame):
    controller.stop(reason='SIGTERM')
