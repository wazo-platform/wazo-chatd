# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo.mallow import fields
from xivo.mallow_helpers import Schema


class UserIdentitySchema(Schema):
    uuid = fields.UUID(dump_only=True)
    backend = fields.String(dump_only=True)
    identity = fields.String(dump_only=True)


class UserIdentityAdminSchema(Schema):
    uuid = fields.UUID(dump_only=True)
    backend = fields.String(required=True)
    identity = fields.String(required=True)
    extra = fields.Dict(load_default=dict)
