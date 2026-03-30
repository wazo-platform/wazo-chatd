# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import unittest
from unittest.mock import Mock

from flask import Flask

from wazo_chatd.connectors.exceptions import ConnectorParseError
from wazo_chatd.connectors.http import ConnectorWebhookResource


class TestConnectorWebhookResource(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)
        self.router = Mock()
        self.resource = ConnectorWebhookResource(self.router)

    def test_post_json_dispatches_to_router(self) -> None:
        self.router.dispatch_webhook.return_value = None

        with self.app.test_request_context(
            '/connectors/incoming/twilio',
            method='POST',
            data=json.dumps({'Body': 'hello', 'From': '+15559876'}),
            content_type='application/json',
        ):
            response, status_code = self.resource.post(backend='twilio')

        self.router.dispatch_webhook.assert_called_once()
        call_args = self.router.dispatch_webhook.call_args
        raw_data = call_args[0][0]
        assert raw_data['Body'] == 'hello'
        assert raw_data['From'] == '+15559876'
        assert call_args[1]['backend'] == 'twilio'
        assert status_code == 204

    def test_post_form_data_dispatches_to_router(self) -> None:
        self.router.dispatch_webhook.return_value = None

        with self.app.test_request_context(
            '/connectors/incoming/twilio',
            method='POST',
            data='Body=hello&From=%2B15559876',
            content_type='application/x-www-form-urlencoded',
        ):
            response, status_code = self.resource.post(backend='twilio')

        call_args = self.router.dispatch_webhook.call_args
        raw_data = call_args[0][0]
        assert raw_data['Body'] == 'hello'
        assert raw_data['From'] == '+15559876'
        assert call_args[1]['backend'] == 'twilio'
        assert status_code == 204

    def test_post_without_backend_hint(self) -> None:
        self.router.dispatch_webhook.return_value = None

        with self.app.test_request_context(
            '/connectors/incoming',
            method='POST',
            data=json.dumps({'Body': 'hello'}),
            content_type='application/json',
        ):
            response, status_code = self.resource.post()

        call_args = self.router.dispatch_webhook.call_args
        assert call_args[1]['backend'] is None
        assert status_code == 204

    def test_post_unknown_backend_returns_404(self) -> None:
        self.router.dispatch_webhook.side_effect = ConnectorParseError('No connector')

        with self.app.test_request_context(
            '/connectors/incoming/nonexistent',
            method='POST',
            data='{}',
            content_type='application/json',
        ):
            response, status_code = self.resource.post(backend='nonexistent')

        assert status_code == 404

    def test_raw_headers_passed_in_metadata(self) -> None:
        self.router.dispatch_webhook.return_value = None

        with self.app.test_request_context(
            '/connectors/incoming/twilio',
            method='POST',
            data=json.dumps({'Body': 'hi'}),
            content_type='application/json',
            headers={'X-Custom-Header': 'test-value'},
        ):
            self.resource.post(backend='twilio')

        call_args = self.router.dispatch_webhook.call_args
        raw_data = call_args[0][0]
        assert '_headers' in raw_data
        assert raw_data['_headers']['X-Custom-Header'] == 'test-value'
