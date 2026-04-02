# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from flask import request
from flask_restful import Resource

from wazo_chatd.plugins.connectors.exceptions import ConnectorParseError
from wazo_chatd.plugins.connectors.types import WebhookData

if TYPE_CHECKING:
    from wazo_chatd.plugins.connectors.router import ConnectorRouter

logger = logging.getLogger(__name__)


class ConnectorWebhookResource(Resource):
    """Shared webhook endpoint for all connector backends.

    Routes:
        ``POST /connectors/incoming`` — tries all connectors
        ``POST /connectors/incoming/<backend>`` — backend hint for fast path

    Extracts the request body and HTTP metadata into a
    :class:`WebhookData`, then dispatches to the router.
    """

    def __init__(self, router: ConnectorRouter) -> None:
        self._router = router

    def post(self, backend: str | None = None) -> tuple[dict[str, Any] | str, int]:
        data = self._build_webhook_data()

        try:
            self._router.dispatch_webhook(data, backend=backend)
        except ConnectorParseError:
            logger.info('No connector matched webhook (backend=%s)', backend)
            return {'error': 'No connector matched the webhook'}, 404

        return '', 204

    def _build_webhook_data(self) -> WebhookData:
        if request.is_json:
            body: dict[str, Any] = request.get_json(force=True) or {}
        else:
            body = request.form.to_dict()

        return WebhookData(
            body=body,
            headers=dict(request.headers),
            content_type=request.content_type or '',
        )


class ConnectorReloadResource(Resource):
    """Reload connector instances from the database.

    Route: ``POST /connectors/reload``

    TODO: Replace with confd client fetch once wazo-confd-mock
    supports chat_provider responses.
    """

    def __init__(self, router: ConnectorRouter) -> None:
        self._router = router

    def post(self) -> tuple[str, int]:
        self._router.load_providers()
        return '', 204
