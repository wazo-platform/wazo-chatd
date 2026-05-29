# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest

import pytest

from wazo_chatd.plugins.connectors.types import ConfigField


class TestConfigFieldValidation(unittest.TestCase):
    def test_valid_field_constructs(self) -> None:
        field = ConfigField(name='api_key', label={'en_US': 'API Key'})

        assert field.name == 'api_key'

    def test_label_missing_en_us_rejected(self) -> None:
        with pytest.raises(ValueError, match='en_US'):
            ConfigField(name='api_key', label={'fr_CA': 'Clé'})

    def test_non_mapping_label_rejected(self) -> None:
        with pytest.raises(ValueError, match='en_US'):
            ConfigField(name='api_key', label='en_US')  # type: ignore[arg-type]

    def test_select_without_choices_rejected(self) -> None:
        with pytest.raises(ValueError, match='choices'):
            ConfigField(name='region', label={'en_US': 'Region'}, type='select')

    def test_select_default_not_in_choices_rejected(self) -> None:
        with pytest.raises(ValueError, match='default'):
            ConfigField(
                name='region',
                label={'en_US': 'Region'},
                type='select',
                default='asia',
                choices=('us', 'eu'),
            )

    def test_choices_on_non_select_rejected(self) -> None:
        with pytest.raises(ValueError, match='choices'):
            ConfigField(name='api_key', label={'en_US': 'API Key'}, choices=('a', 'b'))

    def test_non_select_field_allows_default(self) -> None:
        field = ConfigField(
            name='api_key', label={'en_US': 'API Key'}, default='prefilled'
        )

        assert field.default == 'prefilled'
