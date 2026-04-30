# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import unittest

from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from wazo_chatd.plugin_helpers.http import build_public_url


def _make_request(path: str, headers: dict[str, str] | None = None) -> Request:
    builder = EnvironBuilder(path=path, headers=headers or {})
    return Request(builder.get_environ())


class TestBuildPublicUrl(unittest.TestCase):
    def test_no_forwarded_headers_falls_back_to_request_url(self) -> None:
        request = _make_request('/foo/bar')
        assert build_public_url(request) == 'http://localhost/foo/bar'

    def test_honors_x_forwarded_proto(self) -> None:
        request = _make_request('/foo/bar', {'X-Forwarded-Proto': 'https'})
        assert build_public_url(request) == 'https://localhost/foo/bar'

    def test_honors_x_script_name_prefix(self) -> None:
        request = _make_request('/foo/bar', {'X-Script-Name': '/api/chatd'})
        assert build_public_url(request) == 'http://localhost/api/chatd/foo/bar'

    def test_reconstructs_public_url_behind_wazo_nginx(self) -> None:
        request = _make_request(
            '/foo/bar',
            {
                'Host': 'wazo.example.com',
                'X-Forwarded-Proto': 'https',
                'X-Script-Name': '/api/chatd',
            },
        )
        assert build_public_url(request) == 'https://wazo.example.com/api/chatd/foo/bar'

    def test_preserves_query_string(self) -> None:
        request = _make_request(
            '/foo/bar?tenant=abc&x=1',
            {'X-Forwarded-Proto': 'https', 'X-Script-Name': '/api/chatd'},
        )
        assert build_public_url(request) == (
            'https://localhost/api/chatd/foo/bar?tenant=abc&x=1'
        )
