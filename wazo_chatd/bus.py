# Copyright 2015-2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0+

import kombu
import logging

from contextlib import contextmanager
from threading import Thread
from kombu import (
    Connection,
    Exchange,
    binding,
)
from kombu.mixins import ConsumerMixin

from xivo.pubsub import Pubsub

logger = logging.getLogger(__name__)


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

        self._bus_url = 'amqp://{username}:{password}@{host}:{port}//'.format(**global_config['bus'])
        self._exchange = Exchange(
            global_config['bus']['exchange_name'],
            type=global_config['bus']['exchange_type'],
        )
        self._queue = kombu.Queue(exclusive=True)

    def run(self):
        logger.info("Running AMQP consumer")
        with Connection(self._bus_url) as connection:
            self.connection = connection
            super().run()

    def get_consumers(self, Consumer, channel):
        return [Consumer(self._queue, callbacks=[self._on_bus_message])]

    def on_event(self, routing_key, callback):
        logger.debug('Added callback on event "%s"', routing_key)
        self._queue.bindings.add(binding(self._exchange, routing_key=routing_key))
        self._events_pubsub.subscribe(routing_key, callback)

    def _on_bus_message(self, body, message):
        try:
            event = body['data']
        except KeyError:
            logger.error('Invalid event message received: %s', event)
        else:
            self._events_pubsub.publish(message.delivery_info['routing_key'], event)
        finally:
            message.ack()

    def stop(self):
        self.should_stop = True
