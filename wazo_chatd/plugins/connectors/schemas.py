# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from marshmallow import ValidationError, missing, pre_load, validate
from marshmallow.fields import Function
from xivo.mallow import fields
from xivo.mallow_helpers import ListSchema as _ListSchema
from xivo.mallow_helpers import Schema

from wazo_chatd.plugins.connectors.types import ConfigField

_MAX_EXTRA_KEY_LENGTH = 64
_MAX_EXTRA_VALUE_LENGTH = 1024
_MAX_EXTRA_TOTAL_LENGTH = 4096
_EXTRA_SCALAR_TYPES = (str, int, float, bool, type(None))


def _scalar_length(key: str, item: object) -> int:
    if not isinstance(item, _EXTRA_SCALAR_TYPES):
        raise ValidationError(f'extra[{key!r}] must be a scalar or list of scalars')
    length = len(item) if isinstance(item, str) else len(str(item))
    if length > _MAX_EXTRA_VALUE_LENGTH:
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


def _serialize_label(field: ConfigField) -> list[dict[str, str]]:
    return [
        {'language': locale, 'value': value} for locale, value in field.label.items()
    ]


def _serialize_choices(field: ConfigField) -> list[str]:
    if field.type != 'select':
        return missing  # type: ignore[return-value]
    return list(field.choices)


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
    identity = fields.String(validate=validate.Length(min=1, max=256))
    extra = fields.Dict(validate=_validate_extra)

    @pre_load
    def reject_user_uuid(self, data, **kwargs):
        if 'user_uuid' in data:
            raise ValidationError(
                {'user_uuid': ['Reassignment not supported; delete and recreate.']}
            )
        return data


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
        if 'user_uuid' not in result:
            return result
        values = (
            data.getlist('user_uuid')
            if hasattr(data, 'getlist')
            else [result['user_uuid']]
        )
        pieces = (p for v in values for p in v.split(',') if p)
        result['user_uuid'] = list(dict.fromkeys(pieces))
        return result


class ConnectorSchema(Schema):
    name = fields.String(dump_only=True)
    supported_types = fields.List(fields.String(), dump_only=True)
    configured = fields.Boolean(dump_only=True)
    mode = fields.String(dump_only=True)


class IdentityBindingSchema(Schema):
    identity_uuid = fields.UUID(dump_only=True)
    user_uuid = fields.UUID(dump_only=True)


class ConnectorIdentityItemSchema(Schema):
    identity = fields.String(dump_only=True)
    capabilities = fields.List(fields.String(), dump_only=True)
    binding = fields.Nested(IdentityBindingSchema, dump_only=True, allow_none=True)


class ConfigFieldSchema(Schema):
    name = fields.String(dump_only=True)
    type_ = fields.String(dump_only=True, data_key='type', attribute='type')
    required = fields.Boolean(dump_only=True)
    default = fields.String(dump_only=True)
    label = Function(serialize=_serialize_label, dump_only=True)
    choices = Function(serialize=_serialize_choices, dump_only=True)


class ConnectorAuthSchema(Schema):
    scope = fields.String(dump_only=True)
    fields_list = fields.Nested(
        ConfigFieldSchema,
        many=True,
        dump_only=True,
        data_key='fields',
        attribute='fields',
    )


connector_identity_item_schema = ConnectorIdentityItemSchema()
connector_schema = ConnectorSchema()
config_field_schema = ConfigFieldSchema()
connector_auth_schema = ConnectorAuthSchema()
identity_create_schema = IdentityCreateSchema()
identity_list_request_schema = IdentityListRequestSchema()
identity_schema = IdentitySchema()
identity_update_schema = IdentityUpdateSchema()
user_identity_list_request_schema = UserIdentityListRequestSchema()
user_identity_schema = UserIdentitySchema()
