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
    WebhookParseException,
    WebhookTransientException,
)
from wazo_chatd.plugins.connectors.schemas import (
    connector_inventory_item_schema,
    connector_schema,
    identity_create_schema,
    identity_list_request_schema,
    identity_schema,
    identity_update_schema,
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


class ConnectorListResource(AuthResource):
    def __init__(self, router: ConnectorRouter) -> None:
        self._router = router

    @required_acl('chatd.connectors.read')
    def get(self) -> tuple[dict[str, Any], int]:
        tenant_uuid = get_tenant_uuids(recurse=False)[0]
        items = self._router.list_connectors(tenant_uuid)

        return {
            'items': connector_schema.dump(items, many=True),
            'total': len(items),
        }, 200


class ConnectorInventoryResource(AuthResource):
    def __init__(self, router: ConnectorRouter) -> None:
        self._router = router

    @required_acl('chatd.connectors.{backend}.inventory.read')
    def get(self, backend: str) -> tuple[dict[str, Any], int]:
        tenant_uuid = get_tenant_uuids(recurse=False)[0]
        items = self._router.list_connector_inventory(tenant_uuid, backend)

        return {
            'items': connector_inventory_item_schema.dump(items, many=True),
            'total': len(items),
        }, 200


class IdentityListResource(AuthResource):
    def __init__(self, service: ConnectorService, router: ConnectorRouter) -> None:
        self._service = service
        self._router = router

    @required_acl('chatd.identities.read')
    def get(self) -> tuple[dict[str, Any], int]:
        tenant_uuids = get_tenant_uuids(recurse=True)
        filter_parameters = identity_list_request_schema.load(request.args)

        identities = self._service.list_identities(tenant_uuids, **filter_parameters)
        filtered = self._service.count_identities(tenant_uuids, **filter_parameters)
        total = self._service.count_identities(tenant_uuids)

        return {
            'items': identity_schema.dump(identities, many=True),
            'filtered': filtered,
            'total': total,
        }, 200

    @required_acl('chatd.identities.create')
    def post(self) -> tuple[dict[str, Any], int]:
        tenant_uuids = get_tenant_uuids(recurse=True)
        body = identity_create_schema.load(request.get_json(force=True))

        user_uuid = str(body.pop('user_uuid'))
        tenant_uuid = self._service.get_user_tenant_uuid(tenant_uuids, user_uuid)

        backend = body['backend']
        self._router.validate_tenant_backend(tenant_uuid, backend)

        identity = UserIdentity(
            tenant_uuid=tenant_uuid,
            user_uuid=user_uuid,
            **body,
        )
        created = self._service.create_identity(identity)
        self._router.reconcile_after_create()

        return identity_schema.dump(created), 201


class IdentityItemResource(AuthResource):
    def __init__(self, service: ConnectorService, router: ConnectorRouter) -> None:
        self._service = service
        self._router = router

    @required_acl('chatd.identities.{identity_uuid}.read')
    def get(self, identity_uuid: str) -> tuple[dict[str, Any], int]:
        tenant_uuids = get_tenant_uuids(recurse=True)
        identity = self._service.get_identity(tenant_uuids, identity_uuid)

        return identity_schema.dump(identity), 200

    @required_acl('chatd.identities.{identity_uuid}.update')
    def put(self, identity_uuid: str) -> tuple[dict[str, Any], int]:
        tenant_uuids = get_tenant_uuids(recurse=True)
        identity = self._service.get_identity(tenant_uuids, identity_uuid)
        body = identity_update_schema.load(request.get_json(force=True))

        if 'user_uuid' in body:
            self._service.validate_reassignment_target(
                tenant_uuids, identity, body['user_uuid']
            )

        update_model_instance(identity, body)
        self._service.update_identity(identity)

        return identity_schema.dump(identity), 200

    @required_acl('chatd.identities.{identity_uuid}.delete')
    def delete(self, identity_uuid: str) -> tuple[str, int]:
        tenant_uuids = get_tenant_uuids(recurse=True)
        identity = self._service.get_identity(tenant_uuids, identity_uuid)

        tenant_uuid = str(identity.tenant_uuid)
        backend = str(identity.backend)
        self._service.delete_identity(identity)
        self._router.reconcile_after_delete(tenant_uuid, backend)

        return '', 204


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
