# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from marshmallow import validate
from xivo.mallow import fields
from xivo.mallow_helpers import Schema


class UserIdentitySchema(Schema):
    uuid = fields.UUID(dump_only=True)
    backend = fields.String(required=True, validate=validate.Length(min=1))
    type_ = fields.String(
        required=True, data_key='type', validate=validate.Length(min=1)
    )
    identity = fields.String(required=True, validate=validate.Length(min=1))
    extra = fields.Dict(load_default=dict)


class UserIdentityUpdateSchema(Schema):
    identity = fields.String(required=True, validate=validate.Length(min=1))
    extra = fields.Dict()


class IdentityListRequestSchema(Schema):
    room_uuid = fields.UUID(load_default=None)
