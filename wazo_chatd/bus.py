# Copyright 2019-2020 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from contextlib import contextmanager
from threading import Thread

import kombu

from kombu.mixins import ConsumerMixin

from xivo.status import Status
from xivo.pubsub import Pubsub

from xivo_bus import Marshaler, FailFastPublisher

logger = logging.getLogger(__name__)

ROUTING_KEY_MAPPING = {
    'auth_refresh_token_created': 'auth.users.*.tokens.*.created',
    'auth_refresh_token_deleted': 'auth.users.*.tokens.*.deleted',
    'auth_session_created': 'auth.sessions.*.created',
    'auth_session_deleted': 'auth.sessions.*.deleted',
    'auth_tenant_added': 'auth.tenants.*.created',
    'auth_tenant_deleted': 'auth.tenants.*.deleted',
    'user_created': 'config.user.created',
    'user_deleted': 'config.user.deleted',
    'user_line_associated': 'config.users.*.lines.*.updated',
    'user_line_dissociated': 'config.users.*.lines.*.deleted',
    'users_services_dnd_updated': 'config.users.*.services.dnd.updated',
    'line_device_associated': 'config.lines.*.devices.*.updated',
    'line_device_dissociated': 'config.lines.*.devices.*.deleted',
    'DeviceStateChange': 'ami.DeviceStateChange',
    'Hangup': 'ami.Hangup',
    'Newchannel': 'ami.Newchannel',
    'Newstate': 'ami.Newstate',
    'Hold': 'ami.Hold',
    'Unhold': 'ami.Unhold',
}


@contextmanager
def consumer_thread(consumer):
    thread_name = 'bus_consumer_thread'
    thread = Thread(target=consumer.run, name=thread_name)
    thread.start()
    try:
        yield
    finally:
        logger.debug('stopping bus consumer thread')
        consumer.stop()
        logger.debug('joining bus consumer thread')
        thread.join()


class Consumer(ConsumerMixin):
    def __init__(self, global_config):
        self._events_pubsub = Pubsub()

        self._bus_url = 'amqp://{username}:{password}@{host}:{port}//'.format(
            **global_config['bus']
        )
        self._exchange = kombu.Exchange(
            global_config['bus']['exchange_name'],
            type=global_config['bus']['exchange_type'],
        )
        self._queue = kombu.Queue(exclusive=True)
        self._is_running = False

    def run(self):
        logger.info("Running AMQP consumer")
        with kombu.Connection(self._bus_url) as connection:
            self.connection = connection
            super().run()

    def get_consumers(self, Consumer, channel):
        return [Consumer(self._queue, callbacks=[self._on_bus_message])]

    def on_connection_error(self, exc, interval):
        super().on_connection_error(exc, interval)
        self._is_running = False

    def on_connection_revived(self):
        super().on_connection_revived()
        self._is_running = True

    def is_running(self):
        return self._is_running

    def provide_status(self, status):
        status['bus_consumer']['status'] = (
            Status.ok if self.is_running() else Status.fail
        )

    def on_event(self, event_name, callback):
        logger.debug('Added callback on event "%s"', event_name)
        self._queue.bindings.add(
            kombu.binding(self._exchange, routing_key=ROUTING_KEY_MAPPING[event_name])
        )
        self._events_pubsub.subscribe(event_name, callback)

    def _on_bus_message(self, body, message):
        try:
            event = body['data']
            event_name = body['name']
        except KeyError:
            logger.error('Invalid event message received: %s', event)
        else:
            self._events_pubsub.publish(event_name, event)
        finally:
            message.ack()

    def stop(self):
        self.should_stop = True


# Must be recreated for each request
# TODO can be optimized to be instantiated only once by request
# when the endpoint need to send many messages
class Publisher:
    def __init__(self, config):
        self._config = config['bus']
        self._uuid = config['uuid']
        self._url = 'amqp://{username}:{password}@{host}:{port}//'.format(
            **self._config
        )

    def publish(self, event, headers=None):
        bus_connection = kombu.Connection(self._url)
        bus_exchange = kombu.Exchange(
            self._config['exchange_name'], type=self._config['exchange_type']
        )
        bus_producer = kombu.Producer(
            bus_connection, exchange=bus_exchange, auto_declare=True
        )
        bus_marshaler = Marshaler(self._uuid)
        FailFastPublisher(bus_producer, bus_marshaler).publish(event, headers=headers)
