# Copyright 2019-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from marshmallow import pre_load, validates_schema
from xivo.mallow import fields, validate
from xivo.mallow_helpers import ListSchema as _ListSchema
from xivo.mallow_helpers import Schema, ValidationError


class RoomUserSchema(Schema):
    uuid = fields.UUID()
    tenant_uuid = fields.UUID()
    wazo_uuid = fields.UUID()


class RoomSchema(Schema):
    uuid = fields.UUID(dump_only=True)
    tenant_uuid = fields.UUID(dump_only=True)

    name = fields.String(allow_none=True)

    users = fields.Nested('RoomUserSchema', many=True, missing=list)


class MessageSchema(Schema):
    uuid = fields.UUID(dump_only=True)
    content = fields.String(required=True)
    alias = fields.String(validate=validate.Length(max=256), allow_none=True)
    user_uuid = fields.UUID(dump_only=True)
    tenant_uuid = fields.UUID(dump_only=True)
    wazo_uuid = fields.UUID(dump_only=True)
    created_at = fields.DateTime(dump_only=True)

    room = fields.Nested('RoomSchema', dump_only=True, only=['uuid'])


class ListRequestSchema(_ListSchema):
    default_sort_column = 'created_at'
    sort_columns = ['created_at']
    searchable_columns = []
    default_direction = 'desc'
    from_date = fields.DateTime()


class MessageListRequestSchema(_ListSchema):
    default_sort_column = 'created_at'
    sort_columns = ['created_at']
    searchable_columns = []
    default_direction = 'desc'

    search = fields.String()
    distinct = fields.String(validate=validate.OneOf(['room_uuid']))

    @validates_schema
    def search_or_distinct(self, data, **kwargs):
        if not data.get('search') and not data.get('distinct'):
            raise ValidationError('Missing search or distinct')


class RoomListRequestSchema(Schema):
    user_uuid = fields.List(fields.UUID(), missing=list, attribute='user_uuids')

    @pre_load
    def convert_user_uuid_to_list(self, data, **kwargs):
        result = data.to_dict()
        if data.get('user_uuid'):
            result['user_uuid'] = set(data['user_uuid'].split(','))
        return result
