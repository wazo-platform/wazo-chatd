# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from flask import request
from xivo.auth_verifier import required_acl
from xivo.tenant_flask_helpers import token

from wazo_chatd.http import AuthResource, ErrorCatchingResource
from wazo_chatd.plugin_helpers.http import build_public_url
from wazo_chatd.plugins.connectors.exceptions import (
    ConnectorParseError,
    ConnectorTransientError,
    WebhookParseException,
    WebhookTransientException,
)
from wazo_chatd.plugins.connectors.schemas import (
    user_identity_list_request_schema,
    user_identity_schema,
)
from wazo_chatd.plugins.connectors.services import ConnectorService
from wazo_chatd.plugins.connectors.types import WebhookData

if TYPE_CHECKING:
    from wazo_chatd.plugins.connectors.router import ConnectorRouter

logger = logging.getLogger(__name__)


class ConnectorWebhookResource(ErrorCatchingResource):
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
            raise WebhookParseException() from None
        except ConnectorTransientError as exc:
            logger.warning(
                'Webhook deferred (backend=%s): %s — provider should retry',
                backend,
                exc,
            )
            raise WebhookTransientException() from None

        return '', 204

    def _build_webhook_data(self) -> WebhookData:
        body: Mapping[str, Any]
        if request.is_json:
            body = request.get_json(force=True) or {}
        else:
            body = request.form

        return WebhookData(
            body=body,
            headers=dict(request.headers),
            content_type=request.content_type or '',
            url=build_public_url(request),
        )


class UserMeIdentityListResource(AuthResource):
    def __init__(self, service: ConnectorService) -> None:
        self._service = service

    @required_acl('chatd.users.me.identities.read')
    def get(self) -> tuple[dict[str, Any], int]:
        params = user_identity_list_request_schema.load(request.args)
        user_uuid = str(token.user_uuid)
        tenant_uuids = [token.tenant_uuid]

        if params['room_uuid'] is not None:
            room_uuid = str(params['room_uuid'])
            identities = self._service.list_room_identities(
                tenant_uuids, room_uuid, user_uuid
            )
        else:
            identities = self._service.list_identities(
                tenant_uuids, user_uuid, only_registered=True
            )

        return {
            'items': user_identity_schema.dump(identities, many=True),
            'total': len(identities),
        }, 200
