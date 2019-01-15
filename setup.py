#!/usr/bin/env python3
# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
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
            '{}=wazo_chatd.main:main'.format(NAME),
        ],
        'wazo_chatd.plugins': [
            'api = wazo_chatd.plugins.api.plugin:Plugin',
            'config = wazo_chatd.plugins.config.plugin:Plugin',
            'status = wazo_chatd.plugins.status.plugin:Plugin',
        ],
    },
)
