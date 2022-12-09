#!/usr/bin/env python3
# Copyright 2019-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from setuptools import setup
from setuptools import find_packages


NAME = 'wazo-chatd'
setup(
    name=NAME,
    version='1.0',
    author='Wazo Authors',
    author_email='dev@wazo.community',
    url='http://wazo.community',
    packages=find_packages(),
    package_data={'wazo_chatd.plugins': ['*/api.yml']},
    entry_points={
        'console_scripts': [
            f'{NAME}=wazo_chatd.main:main',
            f'{NAME}-init-db=wazo_chatd.init_db:main',
        ],
        'wazo_chatd.plugins': [
            'api = wazo_chatd.plugins.api.plugin:Plugin',
            'config = wazo_chatd.plugins.config.plugin:Plugin',
            'presences = wazo_chatd.plugins.presences.plugin:Plugin',
            'rooms = wazo_chatd.plugins.rooms.plugin:Plugin',
            'status = wazo_chatd.plugins.status.plugin:Plugin',
            'teams_presence = wazo_chatd.plugins.teams_presence.plugin:Plugin',
        ],
    },
)
