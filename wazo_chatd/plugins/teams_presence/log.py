# Copyright 2022-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging


class _TeamsPrefixLogAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return f'[Microsoft Teams Presence] {msg}', kwargs


def make_logger(name):
    return _TeamsPrefixLogAdapter(logging.getLogger(name), {})
