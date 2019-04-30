# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo.mallow import fields, validate
from xivo.mallow_helpers import Schema, ListSchema as _ListSchema


class RoomUserSchema(Schema):
    uuid = fields.UUID()
    tenant_uuid = fields.UUID()
    wazo_uuid = fields.UUID()


class RoomSchema(Schema):
    uuid = fields.UUID(dump_only=True)
    tenant_uuid = fields.UUID(dump_only=True)

    name = fields.String(allow_none=True)

    users = fields.Nested(
        'RoomUserSchema',
        many=True,
        missing=[],
    )


class MessageSchema(Schema):
    uuid = fields.UUID(dump_only=True)
    content = fields.String(required=True)
    alias = fields.String(validate=validate.Length(max=256), allow_none=True)
    user_uuid = fields.UUID(dump_only=True)
    tenant_uuid = fields.UUID(dump_only=True)
    wazo_uuid = fields.UUID(dump_only=True)
    created_at = fields.DateTime(dump_only=True)

    room = fields.Nested(
        'RoomSchema',
        dump_only=True,
        only=['uuid'],
    )


class ListRequestSchema(_ListSchema):
    default_sort_column = 'created_at'
    sort_columns = ['created_at']
    searchable_columns = []
    default_direction = 'desc'

    class Meta:
        exclude = ('offset', 'search')


class MessageListRequestSchema(_ListSchema):
    default_sort_column = 'created_at'
    sort_columns = ['created_at']
    searchable_columns = []
    default_direction = 'desc'

    class Meta:
        exclude = ('offset',)
        strict = True
