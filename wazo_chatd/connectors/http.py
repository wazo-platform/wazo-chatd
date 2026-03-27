# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import Any

from flask import request
from flask_restful import Resource

from wazo_chatd.connectors.exceptions import ConnectorParseError
from wazo_chatd.connectors.router import ConnectorRouter

logger = logging.getLogger(__name__)


class ConnectorWebhookResource(Resource):
    """Shared webhook endpoint for all connector backends.

    Route: ``POST /connectors/incoming/<backend>``

    Extracts raw data from the request (JSON or form-encoded),
    includes headers as ``_headers`` for signature validation,
    and dispatches to :meth:`ConnectorRouter.dispatch_webhook`.
    """

    def __init__(self, router: ConnectorRouter) -> None:
        self._router = router

    def post(self, backend: str) -> tuple[dict[str, Any] | str, int]:
        raw_data = self._extract_raw_data()

        try:
            self._router.dispatch_webhook(backend, raw_data)
        except ConnectorParseError:
            logger.info('No connector matched backend %r', backend)
            return {'error': f'Unknown backend: {backend}'}, 404

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
