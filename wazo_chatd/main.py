# Copyright 2019-2020 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import sys

from xivo import xivo_logging
from xivo.config_helper import set_xivo_uuid
from xivo.user_rights import change_user

from wazo_chatd import config
from wazo_chatd.controller import Controller

logger = logging.getLogger(__name__)


def main():
    conf = config.load_config(sys.argv[1:])

    if conf['user']:
        change_user(conf['user'])

    xivo_logging.setup_logging(
        conf['log_file'], debug=conf['debug'], log_level=conf['log_level']
    )
    xivo_logging.silence_loggers(
        ['Flask-Cors', 'urllib3', 'stevedore.extension', 'amqp'], logging.WARNING
    )

    set_xivo_uuid(conf, logger)

    controller = Controller(conf)
    controller.run()
