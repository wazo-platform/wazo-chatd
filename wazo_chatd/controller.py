# Copyright 2019-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import signal

from functools import partial
from wazo_auth_client import Client as AuthClient
from xivo import plugin_helpers
from xivo.consul_helpers import ServiceCatalogRegistration
from xivo.status import StatusAggregator
from xivo.token_renewer import TokenRenewer

from .bus import BusConsumer, BusPublisher

from . import auth
from .database.helpers import init_db
from .database.queries import DAO
from .http_server import api, app, CoreRestApi
from .thread_manager import ThreadManager

logger = logging.getLogger(__name__)


class Controller:
    def __init__(self, config):
        init_db(config['db_uri'])
        self._service_discovery_args = [
            'wazo-chatd',
            config['uuid'],
            config['consul'],
            config['service_discovery'],
            config['bus'],
            lambda: True,
        ]
        self.status_aggregator = StatusAggregator()
        self.rest_api = CoreRestApi(config)
        self.bus_consumer = BusConsumer.from_config(config['bus'])
        self.bus_publisher = BusPublisher.from_config(config['uuid'], config['bus'])
        self.thread_manager = ThreadManager()
        auth_client = AuthClient(**config['auth'])
        self.token_renewer = TokenRenewer(auth_client)
        if not app.config['auth'].get('master_tenant_uuid'):
            self.token_renewer.subscribe_to_next_token_details_change(
                auth.init_master_tenant
            )
        plugin_helpers.load(
            namespace='wazo_chatd.plugins',
            names=config['enabled_plugins'],
            dependencies={
                'api': api,
                'config': config,
                'dao': DAO(),
                'bus_consumer': self.bus_consumer,
                'bus_publisher': self.bus_publisher,
                'status_aggregator': self.status_aggregator,
                'thread_manager': self.thread_manager,
                'token_changed_subscribe': self.token_renewer.subscribe_to_token_change,
                'next_token_changed_subscribe': self.token_renewer.subscribe_to_next_token_change,
            },
        )

    def run(self):
        logger.info('wazo-chatd starting...')
        self.status_aggregator.add_provider(self.bus_consumer.provide_status)
        self.status_aggregator.add_provider(auth.provide_status)
        signal.signal(signal.SIGTERM, partial(_sigterm_handler, self))

        with self.thread_manager:
            with self.token_renewer:
                with self.bus_consumer:
                    with ServiceCatalogRegistration(*self._service_discovery_args):
                        self.rest_api.run()

    def stop(self, reason):
        logger.warning('Stopping wazo-chatd: %s', reason)
        self.rest_api.stop()


def _sigterm_handler(controller, signum, frame):
    controller.stop(reason='SIGTERM')
