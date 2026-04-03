# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest
from unittest.mock import Mock

import pytest

from wazo_chatd.plugin_helpers.hooks import Hooks


class TestHooksRegister(unittest.TestCase):
    def setUp(self) -> None:
        self.hooks = Hooks()

    def test_register_callback(self) -> None:
        callback = Mock()

        self.hooks.register('some_event', callback)
        self.hooks.dispatch('some_event', 'payload')

        callback.assert_called_once_with('payload')

    def test_register_multiple_callbacks(self) -> None:
        first = Mock()
        second = Mock()

        self.hooks.register('some_event', first)
        self.hooks.register('some_event', second)
        self.hooks.dispatch('some_event', 'payload')

        first.assert_called_once_with('payload')
        second.assert_called_once_with('payload')


class TestHooksHasSubscribers(unittest.TestCase):
    def setUp(self) -> None:
        self.hooks = Hooks()

    def test_no_subscribers(self) -> None:
        assert self.hooks.has_subscribers('nonexistent') is False

    def test_with_subscriber(self) -> None:
        self.hooks.register('some_event', Mock())

        assert self.hooks.has_subscribers('some_event') is True


class TestHooksDispatch(unittest.TestCase):
    def setUp(self) -> None:
        self.hooks = Hooks()

    def test_dispatch_no_subscribers(self) -> None:
        self.hooks.dispatch('nonexistent', 'payload')

    def test_dispatch_swallows_errors_by_default(self) -> None:
        failing = Mock(side_effect=RuntimeError('boom'))
        surviving = Mock()

        self.hooks.register('some_event', failing)
        self.hooks.register('some_event', surviving)
        self.hooks.dispatch('some_event', 'payload')

        surviving.assert_called_once_with('payload')

    def test_dispatch_propagate_errors(self) -> None:
        failing = Mock(side_effect=RuntimeError('boom'))

        self.hooks.register('some_event', failing)

        with pytest.raises(RuntimeError, match='boom'):
            self.hooks.dispatch('some_event', 'payload', propagate_errors=True)

    def test_dispatch_propagate_errors_stops_on_first_failure(self) -> None:
        failing = Mock(side_effect=RuntimeError('boom'))
        second = Mock()

        self.hooks.register('some_event', failing)
        self.hooks.register('some_event', second)

        with pytest.raises(RuntimeError, match='boom'):
            self.hooks.dispatch('some_event', 'payload', propagate_errors=True)

        second.assert_not_called()

    def test_dispatch_different_topics_are_independent(self) -> None:
        callback_a = Mock()
        callback_b = Mock()

        self.hooks.register('topic_a', callback_a)
        self.hooks.register('topic_b', callback_b)
        self.hooks.dispatch('topic_a', 'payload')

        callback_a.assert_called_once_with('payload')
        callback_b.assert_not_called()
