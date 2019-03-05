# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from marshmallow import post_dump, pre_load

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
    line_state = fields.String(dump_only=True)

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

    @post_dump
    def _set_line_state(self, user):
        merged_state = 'unavailable'
        for line in user['lines']:

            state = line['state']
            if state == 'ringing':
                merged_state = state
            elif state == 'holding' and merged_state != 'ringing':
                merged_state = state
            elif state == 'talking' and merged_state not in ('ringing', 'holding'):
                merged_state = state
            elif state == 'available' and merged_state not in ('ringing', 'holding', 'talking'):
                merged_state = state

        user['line_state'] = merged_state


class ListRequestSchema(Schema):

    recurse = fields.Boolean(missing=False)
    user_uuid = fields.List(fields.String(), missing=[], attribute='uuids')

    @pre_load
    def convert_user_uuid_to_list(self, data):
        result = data.to_dict()
        if data.get('user_uuid'):
            result['user_uuid'] = data['user_uuid'].split(',')
        return result
