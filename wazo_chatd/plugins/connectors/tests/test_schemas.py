# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from uuid import UUID, uuid4

import pytest
from marshmallow import ValidationError
from werkzeug.datastructures import MultiDict

from wazo_chatd.plugins.connectors.schemas import (
    identity_create_schema,
    identity_list_request_schema,
)


class TestIdentityListRequestSchemaUserUuidFilter(unittest.TestCase):
    def test_single_value(self) -> None:
        u = uuid4()

        result = identity_list_request_schema.load(MultiDict([('user_uuid', str(u))]))

        assert result['user_uuids'] == [u]

    def test_comma_separated(self) -> None:
        a, b = uuid4(), uuid4()

        result = identity_list_request_schema.load(
            MultiDict([('user_uuid', f'{a},{b}')])
        )

        assert result['user_uuids'] == [a, b]

    def test_repeated_query_param_merges_all_values(self) -> None:
        a, b, c = uuid4(), uuid4(), uuid4()

        result = identity_list_request_schema.load(
            MultiDict([('user_uuid', str(a)), ('user_uuid', f'{b},{c}')])
        )

        assert sorted(result['user_uuids']) == sorted([a, b, c])

    def test_repeated_with_duplicates_deduplicated(self) -> None:
        a = uuid4()

        result = identity_list_request_schema.load(
            MultiDict([('user_uuid', str(a)), ('user_uuid', str(a))])
        )

        assert result['user_uuids'] == [a]

    def test_absent_defaults_to_empty(self) -> None:
        result = identity_list_request_schema.load(MultiDict([]))

        assert result['user_uuids'] == []

    def test_empty_string_yields_empty_list(self) -> None:
        result = identity_list_request_schema.load(MultiDict([('user_uuid', '')]))

        assert result['user_uuids'] == []

    def test_uuid_objects_returned(self) -> None:
        u = uuid4()

        result = identity_list_request_schema.load(MultiDict([('user_uuid', str(u))]))

        assert all(isinstance(item, UUID) for item in result['user_uuids'])


class TestExtraPerValueCap(unittest.TestCase):
    base: dict[str, object] = {
        'user_uuid': str(uuid4()),
        'backend': 'test',
        'type': 'test',
        'identity': 'test:value',
    }

    def test_string_value_above_cap_rejected(self) -> None:
        with pytest.raises(ValidationError):
            identity_create_schema.load({**self.base, 'extra': {'k': 'x' * 1025}})

    def test_int_value_above_cap_rejected(self) -> None:
        with pytest.raises(ValidationError):
            identity_create_schema.load({**self.base, 'extra': {'k': 10**1025}})

    def test_string_value_at_cap_accepted(self) -> None:
        result = identity_create_schema.load({**self.base, 'extra': {'k': 'x' * 1024}})

        assert result['extra'] == {'k': 'x' * 1024}
