# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo.mallow import fields
from xivo.mallow_helpers import Schema


class UserAliasSchema(Schema):
    uuid = fields.UUID(dump_only=True)
    type = fields.String(dump_only=True, attribute='provider.type_')
    backend = fields.String(dump_only=True, attribute='provider.backend')
    identity = fields.String(dump_only=True)
