# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from marshmallow import post_dump

from xivo.mallow import fields
from xivo.mallow.validate import (
    OneOf,
)
from xivo.mallow_helpers import Schema


class LinePresenceSchema(Schema):
    id = fields.Integer(dump_only=True)
    state = fields.String(dump_only=True)

    @post_dump
    def _set_default_state(self, data):
        data['state'] = data['state'] if data['state'] else 'unavailable'
        return data


class SessionPresenceSchema(Schema):
    uuid = fields.UUID(dump_only=True)
    mobile = fields.Boolean(dump_only=True)


class UserPresenceSchema(Schema):
    uuid = fields.UUID(dump_only=True)
    tenant_uuid = fields.UUID(dump_only=True)

    state = fields.String(
        required=True,
        validate=OneOf(['available', 'unavailable', 'invisible']),
    )
    status = fields.String(allow_none=True)
    sessions = fields.Nested(
        'SessionPresenceSchema',
        many=True,
        dump_only=True
    )
    lines = fields.Nested(
        'LinePresenceSchema',
        many=True,
        dump_only=True
    )


class ListRequestSchema(Schema):

    recurse = fields.Boolean(missing=False)
