# Copyright 2023-2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from .models import CachedUser, CachedEndpoint

LOCAL_CACHE = {
    'users': {},
    'endpoints': {},
}


def get_local_cache() -> dict[str, CachedUser]:
    return LOCAL_CACHE['users']


def get_endpoint_cache() -> dict[str, CachedEndpoint]:
    return LOCAL_CACHE['endpoints']


class CacheDAO:
    from .queries.channel import ChannelCache

    channel = ChannelCache()

    from .queries.endpoint import EndpointCache

    endpoint = EndpointCache()

    from .queries.line import LineCache

    line = LineCache()

    from .queries.refresh_token import RefreshTokenCache

    refresh_token = RefreshTokenCache()

    from .queries.session import SessionCache

    session = SessionCache()

    from .queries.user import UserCache

    user = UserCache()
