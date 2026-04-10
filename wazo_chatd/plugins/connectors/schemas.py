# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo.mallow import fields
from xivo.mallow_helpers import Schema


class UserIdentitySchema(Schema):
    uuid = fields.UUID(dump_only=True)
    backend = fields.String(required=True)
    type_ = fields.String(required=True, data_key='type')
    identity = fields.String(required=True)
    extra = fields.Dict(load_default=dict)
