# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import sys

from xivo import xivo_logging
from xivo.config_helper import set_xivo_uuid
from xivo.daemonize import pidfile_context
from xivo.user_rights import change_user

from wazo_chatd import config
from wazo_chatd.controller import Controller

logger = logging.getLogger(__name__)

FOREGROUND = True  # Always in foreground systemd takes care of daemonizing


def main():
    conf = config.load_config(sys.argv[1:])

    if conf['user']:
        change_user(conf['user'])

    xivo_logging.setup_logging(
        conf['log_file'], FOREGROUND, conf['debug'], conf['log_level']
    )
    xivo_logging.silence_loggers(
        ['Flask-Cors', 'urllib3', 'stevedore.extension', 'amqp'], logging.WARNING
    )

    set_xivo_uuid(conf, logger)

    controller = Controller(conf)
    with pidfile_context(conf['pid_file'], FOREGROUND):
        controller.run()
