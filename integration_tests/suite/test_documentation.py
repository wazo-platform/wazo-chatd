# Copyright 2019-2020 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import requests
import yaml

import pytest

from openapi_spec_validator import validate_v2_spec
from .helpers.base import APIIntegrationTest, APIAssetLaunchingTestCase

requests.packages.urllib3.disable_warnings()

logger = logging.getLogger('openapi_spec_validator')
logger.setLevel(logging.INFO)


@pytest.mark.usefixtures('base')
class TestDocumentation(APIIntegrationTest):
    def test_documentation_errors(self):
        port = APIAssetLaunchingTestCase.service_port(9304, 'chatd')
        api_url = f'http://localhost:{port}/1.0/api/api.yml'
        api = requests.get(api_url)
        validate_v2_spec(yaml.safe_load(api.text))
