# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo.mallow import fields
from xivo.mallow_helpers import Schema


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
