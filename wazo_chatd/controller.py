# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import signal

from functools import partial
from xivo import plugin_helpers
from xivo.consul_helpers import ServiceCatalogRegistration
from xivo.status import StatusAggregator

from . import bus
from .database.helpers import init_db
from .http_server import api, CoreRestApi

logger = logging.getLogger(__name__)


class Controller:

    def __init__(self, config):
        init_db(config['db_uri'])
        self._service_discovery_args = [
            'wazo-chatd',
            config.get('uuid'),
            config['consul'],
            config['service_discovery'],
            config['bus'],
            lambda: True,
        ]
        self.status_aggregator = StatusAggregator()
        self.rest_api = CoreRestApi(config)
        self.bus_consumer = bus.Consumer(config)
        plugin_helpers.load(
            namespace='wazo_chatd.plugins',
            names=config['enabled_plugins'],
            dependencies={
                'api': api,
                'config': config,
                'bus_consumer': self.bus_consumer,
                'status_aggregator': self.status_aggregator,
            }
        )

    def run(self):
        logger.info('wazo-chatd starting...')
        self.status_aggregator.add_provider(self.bus_consumer.provide_status)
        signal.signal(signal.SIGTERM, partial(_sigterm_handler, self))

        with bus.consumer_thread(self.bus_consumer):
            with ServiceCatalogRegistration(*self._service_discovery_args):
                self.rest_api.run()

    def stop(self, reason):
        logger.warning('Stopping wazo-chatd: %s', reason)
        self.rest_api.stop()


def _sigterm_handler(controller, signum, frame):
    controller.stop(reason='SIGTERM')
