# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from marshmallow import fields as ma_fields
from marshmallow import post_dump, pre_load, validates_schema
from xivo.mallow import fields, validate
from xivo.mallow_helpers import ListSchema as _ListSchema
from xivo.mallow_helpers import Schema, ValidationError


class RoomUserSchema(Schema):
    uuid = fields.UUID()
    tenant_uuid = fields.UUID()
    wazo_uuid = fields.UUID()
    identity = fields.String(allow_none=True)


class RoomSchema(Schema):
    uuid = fields.UUID(dump_only=True)
    tenant_uuid = fields.UUID(dump_only=True)

    name = fields.String(allow_none=True)

    users = fields.Nested('RoomUserSchema', many=True, load_default=list)


class MessageDeliverySchema(Schema):
    type = fields.String(dump_default='internal', attribute='type_')
    backend = fields.String(dump_default=None, allow_none=True)
    status = fields.String(dump_default='delivered')


class MessageSchema(Schema):
    uuid = fields.UUID(dump_only=True)
    content = fields.String(required=True)
    alias = fields.String(validate=validate.Length(max=256), allow_none=True)
    delivery = fields.Nested(MessageDeliverySchema, dump_only=True, attribute='meta')
    user_uuid = fields.UUID(dump_only=True)
    tenant_uuid = fields.UUID(dump_only=True)
    wazo_uuid = fields.UUID(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    sender_identity_uuid = fields.UUID(load_only=True, allow_none=True)

    room = fields.Nested('RoomSchema', dump_only=True, only=['uuid'])

    @post_dump
    def _default_delivery(self, data: dict, **kwargs: object) -> dict:
        if data.get('delivery') is None:
            data['delivery'] = MessageDeliverySchema().dump({})
        return data


class ListRequestSchema(_ListSchema):
    default_sort_column = 'created_at'
    sort_columns = ['created_at']
    searchable_columns: list[str] = []
    default_direction = 'desc'
    from_date = fields.DateTime()


class MessageListRequestSchema(_ListSchema):
    default_sort_column = 'created_at'
    sort_columns = ['created_at']
    searchable_columns: list[str] = []
    default_direction = 'desc'

    search = fields.String()
    distinct = fields.String(validate=validate.OneOf(['room_uuid']))

    @validates_schema
    def search_or_distinct(self, data, **kwargs):
        if not data.get('search') and not data.get('distinct'):
            raise ValidationError('Missing search or distinct')


class RoomListRequestSchema(Schema):
    user_uuid = fields.List(fields.UUID(), load_default=list, attribute='user_uuids')

    @pre_load
    def convert_user_uuid_to_list(self, data, **kwargs):
        result = data.to_dict()
        if data.get('user_uuid'):
            result['user_uuid'] = set(data['user_uuid'].split(','))
        return result
