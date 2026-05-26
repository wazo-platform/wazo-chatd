# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from marshmallow import ValidationError
from werkzeug.datastructures import MultiDict

from wazo_chatd.plugins.connectors.schemas import (
    identity_create_schema,
    identity_list_request_schema,
    identity_update_schema,
    user_identity_schema,
)


def _identity_stub(extra: dict[str, object] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        uuid=uuid4(),
        tenant_uuid=uuid4(),
        user_uuid=uuid4(),
        backend='test',
        type_='test',
        identity='test:value',
        extra=extra if extra is not None else {},
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


class TestExtraNonScalarRejected(unittest.TestCase):
    base: dict[str, object] = {
        'user_uuid': str(uuid4()),
        'backend': 'test',
        'type': 'test',
        'identity': 'test:value',
    }

    def test_dict_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            identity_create_schema.load(
                {**self.base, 'extra': {'k': {'nested': 'value'}}}
            )

    def test_nested_list_rejected(self) -> None:
        with pytest.raises(ValidationError):
            identity_create_schema.load({**self.base, 'extra': {'k': [[1, 2]]}})


class TestExtraKeyLengthCap(unittest.TestCase):
    base: dict[str, object] = {
        'user_uuid': str(uuid4()),
        'backend': 'test',
        'type': 'test',
        'identity': 'test:value',
    }

    def test_oversized_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            identity_create_schema.load({**self.base, 'extra': {'k' * 65: 'v'}})

    def test_key_at_cap_accepted(self) -> None:
        key = 'k' * 64
        result = identity_create_schema.load({**self.base, 'extra': {key: 'v'}})

        assert result['extra'] == {key: 'v'}


class TestExtraTotalLengthCap(unittest.TestCase):
    base: dict[str, object] = {
        'user_uuid': str(uuid4()),
        'backend': 'test',
        'type': 'test',
        'identity': 'test:value',
    }

    def test_many_small_entries_exceeding_total_rejected(self) -> None:
        extra = {f'k{i:02d}': 'v' * 60 for i in range(70)}

        with pytest.raises(ValidationError):
            identity_create_schema.load({**self.base, 'extra': extra})


class TestExtraAcceptsAllScalarTypes(unittest.TestCase):
    base: dict[str, object] = {
        'user_uuid': str(uuid4()),
        'backend': 'test',
        'type': 'test',
        'identity': 'test:value',
    }

    def test_bool_accepted(self) -> None:
        result = identity_create_schema.load({**self.base, 'extra': {'k': True}})

        assert result['extra'] == {'k': True}

    def test_float_accepted(self) -> None:
        result = identity_create_schema.load({**self.base, 'extra': {'k': 1.5}})

        assert result['extra'] == {'k': 1.5}

    def test_none_accepted(self) -> None:
        result = identity_create_schema.load({**self.base, 'extra': {'k': None}})

        assert result['extra'] == {'k': None}

    def test_list_of_scalars_accepted(self) -> None:
        value: list[object] = [1, 1.5, 'three', None, True]
        result = identity_create_schema.load({**self.base, 'extra': {'k': value}})

        assert result['extra'] == {'k': value}


class TestIdentityCreateSchemaUserUuidLoadOnly(unittest.TestCase):
    base: dict[str, object] = {
        'backend': 'test',
        'type': 'test',
        'identity': 'test:value',
    }

    def test_user_uuid_required_on_load(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            identity_create_schema.load(self.base)

        assert 'user_uuid' in exc_info.value.messages

    def test_user_uuid_not_emitted_on_dump(self) -> None:
        result = identity_create_schema.dump(_identity_stub())

        assert 'user_uuid' not in result


class TestUserIdentitySchemaFields(unittest.TestCase):
    def test_dump_emits_only_public_fields(self) -> None:
        result = user_identity_schema.dump(_identity_stub({'admin_only': 'secret'}))

        assert set(result.keys()) == {'uuid', 'backend', 'type', 'identity'}


class TestIdentityUpdateSchemaRejectsReassignment(unittest.TestCase):
    def test_user_uuid_in_body_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            identity_update_schema.load({'user_uuid': str(uuid4())})

        assert 'user_uuid' in exc_info.value.messages

    def test_user_uuid_with_other_fields_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            identity_update_schema.load(
                {'user_uuid': str(uuid4()), 'identity': 'test:value'}
            )

        assert 'user_uuid' in exc_info.value.messages

    def test_other_fields_alone_accepted(self) -> None:
        result = identity_update_schema.load({'identity': 'test:value'})

        assert result == {'identity': 'test:value'}
