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


class ListRequestSchema(_ListSchema):
    default_sort_column = 'created_at'
    sort_columns = ['created_at']
    searchable_columns = []

    def on_bind_field(self, field_name, field_obj):
        super().on_bind_field(field_name, field_obj)
        # TODO add configurable missing direction to lib-python
        if field_name == 'direction':
            field_obj.missing = 'desc'

    class Meta:
        exclude = ('offset', 'search')
