# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from marshmallow import validate
from xivo.mallow import fields
from xivo.mallow_helpers import Schema


class IdentitySchema(Schema):
    uuid = fields.UUID(dump_only=True)
    tenant_uuid = fields.UUID(dump_only=True)
    user_uuid = fields.UUID(dump_only=True)
    backend = fields.String(required=True, validate=validate.Length(min=1))
    type_ = fields.String(
        required=True, data_key='type', validate=validate.Length(min=1)
    )
    identity = fields.String(required=True, validate=validate.Length(min=1))
    extra = fields.Dict(load_default=dict)


class UserIdentitySchema(IdentitySchema):
    class Meta:
        fields = ('uuid', 'backend', 'type_', 'identity')


class IdentityCreateSchema(Schema):
    user_uuid = fields.UUID(required=True)
    backend = fields.String(required=True, validate=validate.Length(min=1))
    type_ = fields.String(
        required=True, data_key='type', validate=validate.Length(min=1)
    )
    identity = fields.String(required=True, validate=validate.Length(min=1))
    extra = fields.Dict(load_default=dict)


class IdentityUpdateSchema(Schema):
    user_uuid = fields.UUID()
    identity = fields.String(validate=validate.Length(min=1))
    extra = fields.Dict()


class UserIdentityListRequestSchema(Schema):
    room_uuid = fields.UUID(load_default=None)


class ConnectorSchema(Schema):
    name = fields.String(dump_only=True)
    supported_types = fields.List(fields.String(), dump_only=True)
    configured = fields.Boolean(dump_only=True)
    webhook_url = fields.String(dump_only=True)


connector_schema = ConnectorSchema()
identity_create_schema = IdentityCreateSchema()
identity_schema = IdentitySchema()
identity_update_schema = IdentityUpdateSchema()
user_identity_list_request_schema = UserIdentityListRequestSchema()
user_identity_schema = UserIdentitySchema()
