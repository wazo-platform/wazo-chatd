# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from xivo.mallow import fields
from xivo.mallow.validate import (
    OneOf,
)
from xivo.mallow_helpers import Schema


class UserPresenceSchema(Schema):
    uuid = fields.UUID(dump_only=True)
    tenant_uuid = fields.UUID(dump_only=True)

    state = fields.String(
        required=True,
        validate=OneOf(['available', 'unavailable', 'invisible']),
    )
    status = fields.String(allow_none=True)


class ListRequestSchema(Schema):

    recurse = fields.Boolean(missing=False)
