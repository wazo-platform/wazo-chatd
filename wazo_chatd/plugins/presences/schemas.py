# Copyright 2019-2021 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from marshmallow import post_dump, pre_load

from xivo.mallow import fields
from xivo.mallow.validate import OneOf
from xivo.mallow_helpers import Schema


class LinePresenceSchema(Schema):
    id = fields.Integer(dump_only=True)
    state = fields.String(dump_only=True)

    @post_dump(pass_original=True)
    def _set_state(self, data, raw_data):
        # TODO: Add 'progressing'
        if 'ringing' in raw_data.channels_state:
            merged_state = 'ringing'
        elif 'holding' in raw_data.channels_state:
            merged_state = 'holding'
        elif 'talking' in raw_data.channels_state:
            merged_state = 'talking'
        else:
            merged_state = raw_data.endpoint_state or 'unavailable'

        data['state'] = merged_state
        return data


class SessionPresenceSchema(Schema):
    uuid = fields.UUID(dump_only=True)
    mobile = fields.Boolean(dump_only=True)


class UserPresenceSchema(Schema):
    uuid = fields.UUID(dump_only=True)
    tenant_uuid = fields.UUID(dump_only=True)

    state = fields.String(
        required=True, validate=OneOf(['available', 'unavailable', 'invisible', 'away'])
    )
    status = fields.String(allow_none=True)
    last_activity = fields.DateTime(dump_only=True)
    line_state = fields.String(dump_only=True)
    mobile = fields.Boolean(dump_only=True)
    do_not_disturb = fields.Boolean(dump_only=True)
    connected = fields.Boolean(dump_only=True)

    sessions = fields.Nested('SessionPresenceSchema', many=True, dump_only=True)
    lines = fields.Nested('LinePresenceSchema', many=True, dump_only=True)

    @post_dump
    def _set_line_state(self, user):
        line_states = [line['state'] for line in user['lines']]
        # TODO: Add 'progressing'
        if 'ringing' in line_states:
            merged_state = 'ringing'
        elif 'holding' in line_states:
            merged_state = 'holding'
        elif 'talking' in line_states:
            merged_state = 'talking'
        elif 'available' in line_states:
            merged_state = 'available'
        else:
            merged_state = 'unavailable'

        user['line_state'] = merged_state
        return user

    @post_dump(pass_original=True)
    def _set_mobile(self, user, raw_user):
        for token in raw_user.refresh_tokens:
            if token.mobile is True:
                user['mobile'] = True
                return user

        for session in raw_user.sessions:
            if session.mobile is True:
                user['mobile'] = True
                return user

        user['mobile'] = False
        return user

    @post_dump(pass_original=True)
    def _set_connected(self, user, raw_user):
        user['connected'] = True if raw_user.sessions else False
        return user


class ListRequestSchema(Schema):

    recurse = fields.Boolean(missing=False)
    user_uuid = fields.List(fields.UUID(), missing=[], attribute='uuids')

    @pre_load
    def convert_user_uuid_to_list(self, data):
        result = data.to_dict()
        if data.get('user_uuid'):
            result['user_uuid'] = data['user_uuid'].split(',')
        return result
