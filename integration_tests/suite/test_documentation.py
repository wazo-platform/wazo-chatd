# Copyright 2019-2020 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import requests
import yaml

from openapi_spec_validator import validate_v2_spec

from .helpers.base import BaseIntegrationTest
from .helpers.wait_strategy import RestApiOkWaitStrategy

requests.packages.urllib3.disable_warnings()

logger = logging.getLogger('openapi_spec_validator')
logger.setLevel(logging.INFO)


class TestDocumentation(BaseIntegrationTest):

    asset = 'documentation'
    wait_strategy = RestApiOkWaitStrategy()

    def test_documentation_errors(self):
        port = self.service_port(9304, 'chatd')
        api_url = f'http://localhost:{port}/1.0/api/api.yml'
        api = requests.get(api_url)
        validate_v2_spec(yaml.safe_load(api.text))
