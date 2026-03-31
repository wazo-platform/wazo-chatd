# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import Any

from flask import request
from flask_restful import Resource

from typing import TYPE_CHECKING

from wazo_chatd.connectors.exceptions import ConnectorParseError

if TYPE_CHECKING:
    from wazo_chatd.connectors.router import ConnectorRouter

logger = logging.getLogger(__name__)


class ConnectorWebhookResource(Resource):
    """Shared webhook endpoint for all connector backends.

    Routes:
        ``POST /connectors/incoming`` — tries all connectors
        ``POST /connectors/incoming/<backend>`` — backend hint for fast path

    Extracts raw data from the request (JSON or form-encoded),
    includes headers as ``_headers`` for signature validation,
    and dispatches to :meth:`ConnectorRouter.dispatch_webhook`.
    """

    def __init__(self, router: ConnectorRouter) -> None:
        self._router = router

    def post(self, backend: str | None = None) -> tuple[dict[str, Any] | str, int]:
        raw_data = self._extract_raw_data()

        try:
            self._router.dispatch_webhook(raw_data, backend=backend)
        except ConnectorParseError:
            logger.info('No connector matched webhook (backend=%s)', backend)
            return {'error': 'No connector matched the webhook'}, 404

        return '', 204

    def _extract_raw_data(self) -> dict[str, Any]:
        """Extract request body as a plain dict, with headers included.

        Supports both JSON and form-encoded payloads.  Headers are
        attached under the ``_headers`` key so connectors can validate
        signatures without accessing Flask's request object.
        """
        if request.is_json:
            data: dict[str, Any] = request.get_json(force=True) or {}
        else:
            data = request.form.to_dict()

        data['_headers'] = dict(request.headers)
        data['_content_type'] = request.content_type or ''

        return data


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


