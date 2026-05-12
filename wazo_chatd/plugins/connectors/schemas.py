# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from marshmallow import ValidationError, pre_load, validate
from xivo.mallow import fields
from xivo.mallow_helpers import ListSchema as _ListSchema
from xivo.mallow_helpers import Schema

_MAX_EXTRA_KEY_LENGTH = 64
_MAX_EXTRA_VALUE_LENGTH = 1024
_MAX_EXTRA_TOTAL_LENGTH = 4096
_EXTRA_SCALAR_TYPES = (str, int, float, bool, type(None))


def _scalar_length(key: str, item: object) -> int:
    if not isinstance(item, _EXTRA_SCALAR_TYPES):
        raise ValidationError(f'extra[{key!r}] must be a scalar or list of scalars')
    length = len(item) if isinstance(item, str) else len(str(item))
    if isinstance(item, str) and length > _MAX_EXTRA_VALUE_LENGTH:
        raise ValidationError(f'extra[{key!r}] exceeds {_MAX_EXTRA_VALUE_LENGTH} chars')
    return length


def _validate_extra(value: dict) -> None:
    total = 0
    for key, item in value.items():
        if len(key) > _MAX_EXTRA_KEY_LENGTH:
            raise ValidationError(
                f'extra key {key!r} exceeds {_MAX_EXTRA_KEY_LENGTH} chars'
            )
        elements = item if isinstance(item, list) else [item]
        total += len(key) + sum(_scalar_length(key, e) for e in elements)
        if total > _MAX_EXTRA_TOTAL_LENGTH:
            raise ValidationError(
                f'extra total length exceeds {_MAX_EXTRA_TOTAL_LENGTH} chars'
            )


class IdentitySchema(Schema):
    uuid = fields.UUID(dump_only=True)
    tenant_uuid = fields.UUID(dump_only=True)
    user_uuid = fields.UUID(dump_only=True)
    backend = fields.String(required=True, validate=validate.Length(min=1, max=64))
    type_ = fields.String(
        required=True, data_key='type', validate=validate.Length(min=1, max=32)
    )
    identity = fields.String(required=True, validate=validate.Length(min=1, max=256))
    extra = fields.Dict(load_default=dict, validate=_validate_extra)


class UserIdentitySchema(IdentitySchema):
    class Meta:
        fields = ('uuid', 'backend', 'type_', 'identity')


class IdentityCreateSchema(IdentitySchema):
    user_uuid = fields.UUID(required=True, load_only=True)


class IdentityUpdateSchema(Schema):
    user_uuid = fields.UUID()
    identity = fields.String(validate=validate.Length(min=1, max=256))
    extra = fields.Dict(validate=_validate_extra)


class UserIdentityListRequestSchema(Schema):
    room_uuid = fields.UUID(load_default=None)


class IdentityListRequestSchema(_ListSchema):
    default_sort_column = 'identity'
    sort_columns = ['uuid', 'backend', 'type', 'identity']
    default_direction = 'asc'

    user_uuid = fields.List(fields.UUID(), load_default=list, attribute='user_uuids')
    backend = fields.String(load_default=None)
    type_ = fields.String(data_key='type', load_default=None)
    identity = fields.String(load_default=None)

    @pre_load
    def split_user_uuid(self, data, **kwargs):
        result = data.to_dict() if hasattr(data, 'to_dict') else dict(data)
        if data.get('user_uuid'):
            result['user_uuid'] = [u for u in data['user_uuid'].split(',') if u]
        return result


class ConnectorSchema(Schema):
    name = fields.String(dump_only=True)
    supported_types = fields.List(fields.String(), dump_only=True)
    configured = fields.Boolean(dump_only=True)
    webhook_url = fields.String(dump_only=True)


class IdentityBindingSchema(Schema):
    uuid = fields.UUID(dump_only=True)
    user_uuid = fields.UUID(dump_only=True)


class ConnectorInventoryItemSchema(Schema):
    identity = fields.String(dump_only=True)
    type_ = fields.String(dump_only=True, data_key='type')
    binding = fields.Nested(IdentityBindingSchema, dump_only=True, allow_none=True)


connector_inventory_item_schema = ConnectorInventoryItemSchema()
connector_schema = ConnectorSchema()
identity_create_schema = IdentityCreateSchema()
identity_list_request_schema = IdentityListRequestSchema()
identity_schema = IdentitySchema()
identity_update_schema = IdentityUpdateSchema()
user_identity_list_request_schema = UserIdentityListRequestSchema()
user_identity_schema = UserIdentitySchema()
