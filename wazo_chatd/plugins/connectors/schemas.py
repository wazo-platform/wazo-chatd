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


class UserIdentityListRequestSchema(Schema):
    room_uuid = fields.UUID(load_default=None)


identity_schema = IdentitySchema()
user_identity_schema = UserIdentitySchema()
user_identity_list_request_schema = UserIdentityListRequestSchema()
