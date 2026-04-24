# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import unittest
from unittest.mock import Mock

from flask import Flask

from wazo_chatd.plugins.connectors.exceptions import ConnectorParseError
from wazo_chatd.plugins.connectors.http import ConnectorWebhookResource
from wazo_chatd.plugins.connectors.types import WebhookData


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
        data = call_args[0][0]
        assert isinstance(data, WebhookData)
        assert data.body['Body'] == 'hello'
        assert data.body['From'] == '+15559876'
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
        data = call_args[0][0]
        assert isinstance(data, WebhookData)
        assert data.body['Body'] == 'hello'
        assert data.body['From'] == '+15559876'
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

    def test_post_unrecognized_payload_returns_400(self) -> None:
        self.router.dispatch_webhook.side_effect = ConnectorParseError('No connector')

        with self.app.test_request_context(
            '/connectors/incoming/nonexistent',
            method='POST',
            data='{}',
            content_type='application/json',
        ):
            response, status_code = self.resource.post(backend='nonexistent')

        assert status_code == 400

    def test_headers_passed_in_webhook_data(self) -> None:
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
        data = call_args[0][0]
        assert isinstance(data, WebhookData)
        assert data.headers['X-Custom-Header'] == 'test-value'
        assert data.content_type == 'application/json'

    def test_url_without_forwarded_headers_falls_back_to_request_url(self) -> None:
        self.router.dispatch_webhook.return_value = None

        with self.app.test_request_context(
            '/connectors/incoming/twilio',
            method='POST',
            data='Body=hi',
            content_type='application/x-www-form-urlencoded',
        ):
            self.resource.post(backend='twilio')

        data = self.router.dispatch_webhook.call_args[0][0]
        assert data.url == 'http://localhost/connectors/incoming/twilio'

    def test_url_honors_forwarded_proto(self) -> None:
        self.router.dispatch_webhook.return_value = None

        with self.app.test_request_context(
            '/connectors/incoming/twilio',
            method='POST',
            data='Body=hi',
            content_type='application/x-www-form-urlencoded',
            headers={'X-Forwarded-Proto': 'https'},
        ):
            self.resource.post(backend='twilio')

        data = self.router.dispatch_webhook.call_args[0][0]
        assert data.url == 'https://localhost/connectors/incoming/twilio'

    def test_url_honors_x_script_name_prefix(self) -> None:
        self.router.dispatch_webhook.return_value = None

        with self.app.test_request_context(
            '/connectors/incoming/twilio',
            method='POST',
            data='Body=hi',
            content_type='application/x-www-form-urlencoded',
            headers={'X-Script-Name': '/api/chatd'},
        ):
            self.resource.post(backend='twilio')

        data = self.router.dispatch_webhook.call_args[0][0]
        assert data.url == 'http://localhost/api/chatd/connectors/incoming/twilio'

    def test_url_reconstructs_public_url_behind_wazo_nginx(self) -> None:
        self.router.dispatch_webhook.return_value = None

        with self.app.test_request_context(
            '/connectors/incoming/twilio',
            method='POST',
            data='Body=hi',
            content_type='application/x-www-form-urlencoded',
            headers={
                'Host': 'wazo.example.com',
                'X-Forwarded-Proto': 'https',
                'X-Script-Name': '/api/chatd',
            },
        ):
            self.resource.post(backend='twilio')

        data = self.router.dispatch_webhook.call_args[0][0]
        assert data.url == (
            'https://wazo.example.com/api/chatd/connectors/incoming/twilio'
        )

    def test_url_preserves_query_string(self) -> None:
        self.router.dispatch_webhook.return_value = None

        with self.app.test_request_context(
            '/connectors/incoming/twilio?tenant=abc',
            method='POST',
            data='Body=hi',
            content_type='application/x-www-form-urlencoded',
            headers={'X-Forwarded-Proto': 'https', 'X-Script-Name': '/api/chatd'},
        ):
            self.resource.post(backend='twilio')

        data = self.router.dispatch_webhook.call_args[0][0]
        assert data.url == (
            'https://localhost/api/chatd/connectors/incoming/twilio?tenant=abc'
        )
