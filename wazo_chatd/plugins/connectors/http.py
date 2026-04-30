# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from flask import request
from xivo.auth_verifier import required_acl
from xivo.tenant_flask_helpers import token

from wazo_chatd.database.models import UserIdentity
from wazo_chatd.http import AuthResource, ErrorCatchingResource
from wazo_chatd.plugin_helpers.http import build_public_url, update_model_instance
from wazo_chatd.plugin_helpers.tenant import get_tenant_uuids
from wazo_chatd.plugins.connectors.exceptions import (
    ConnectorParseError,
    ConnectorTransientError,
)
from wazo_chatd.plugins.connectors.schemas import (
    IdentityListRequestSchema,
    UserIdentitySchema,
    UserIdentityUpdateSchema,
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
            return {'error': 'Unrecognized request'}, 400
        except ConnectorTransientError as exc:
            logger.warning(
                'Webhook deferred (backend=%s): %s — provider should retry',
                backend,
                exc,
            )
            return {'error': 'Service temporarily unavailable'}, 503

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


class UserIdentityListResource(AuthResource):
    def __init__(self, service: ConnectorService, router: ConnectorRouter) -> None:
        self._service = service
        self._router = router

    @required_acl('chatd.users.{user_uuid}.identities.read')
    def get(self, user_uuid: str) -> tuple[dict[str, Any], int]:
        tenant_uuids = get_tenant_uuids(recurse=True)
        identities = self._service.list_identities(tenant_uuids, user_uuid)
        return {
            'items': UserIdentitySchema().dump(identities, many=True),
            'total': len(identities),
        }, 200

    @required_acl('chatd.users.{user_uuid}.identities.create')
    def post(self, user_uuid: str) -> tuple[dict[str, Any], int]:
        tenant_uuids = get_tenant_uuids(recurse=True)
        body = UserIdentitySchema().load(request.get_json(force=True))
        tenant_uuid = self._service.get_user_tenant_uuid(tenant_uuids, user_uuid)
        backend = body['backend']
        self._router.validate_tenant_backend(tenant_uuid, backend)
        identity = UserIdentity(
            tenant_uuid=tenant_uuid,
            user_uuid=user_uuid,
            **body,
        )
        created = self._service.create_identity(identity)
        self._router.reconcile_tenant_backend(tenant_uuid, backend)
        return UserIdentitySchema().dump(created), 201


class UserIdentityItemResource(AuthResource):
    def __init__(self, service: ConnectorService, router: ConnectorRouter) -> None:
        self._service = service
        self._router = router

    @required_acl('chatd.users.{user_uuid}.identities.{identity_uuid}.read')
    def get(self, user_uuid: str, identity_uuid: str) -> tuple[dict[str, Any], int]:
        tenant_uuids = get_tenant_uuids(recurse=True)
        identity = self._service.get_identity(
            tenant_uuids, identity_uuid, user_uuid=user_uuid
        )
        return UserIdentitySchema().dump(identity), 200

    @required_acl('chatd.users.{user_uuid}.identities.{identity_uuid}.update')
    def put(self, user_uuid: str, identity_uuid: str) -> tuple[dict[str, Any], int]:
        tenant_uuids = get_tenant_uuids(recurse=True)
        identity = self._service.get_identity(
            tenant_uuids, identity_uuid, user_uuid=user_uuid
        )
        body = UserIdentityUpdateSchema().load(request.get_json(force=True))
        update_model_instance(identity, body)
        self._service.update_identity(identity)
        return UserIdentitySchema().dump(identity), 200

    @required_acl('chatd.users.{user_uuid}.identities.{identity_uuid}.delete')
    def delete(self, user_uuid: str, identity_uuid: str) -> tuple[str, int]:
        tenant_uuids = get_tenant_uuids(recurse=True)
        identity = self._service.get_identity(
            tenant_uuids, identity_uuid, user_uuid=user_uuid
        )
        tenant_uuid = str(identity.tenant_uuid)
        backend = str(identity.backend)
        self._service.delete_identity(identity)
        self._router.reconcile_tenant_backend(tenant_uuid, backend)
        return '', 204


class UserMeIdentityListResource(AuthResource):
    def __init__(self, service: ConnectorService) -> None:
        self._service = service

    @required_acl('chatd.users.me.identities.read')
    def get(self) -> tuple[dict[str, Any], int]:
        params = IdentityListRequestSchema().load(request.args)
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
            'items': UserIdentitySchema(
                only=('uuid', 'backend', 'type_', 'identity')
            ).dump(identities, many=True),
            'total': len(identities),
        }, 200
