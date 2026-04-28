# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from asyncio import CancelledError
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

_POSTGRES_SERVER_SETTINGS_PARAMS: tuple[str, ...] = (
    'application_name',
    'search_path',
    'options',
    'statement_timeout',
    'lock_timeout',
    'idle_in_transaction_session_timeout',
)

_current_session: ContextVar[AsyncSession] = ContextVar('_current_session')


def get_async_session() -> AsyncSession:
    return _current_session.get()


def build_asyncpg_connect_args(uri: str) -> tuple[str, dict[str, Any]]:
    """Translate a Postgres URI into (driver_uri, connect_args) for asyncpg.

    ``sslmode`` is translated into an ``ssl`` bool and Postgres GUCs
    (e.g. ``application_name``) are routed through ``server_settings``.
    Any ``+dialect`` suffix in the URI scheme is stripped so the result
    is directly usable by ``asyncpg.connect()``. SQLAlchemy callers
    must re-apply the ``+asyncpg`` dialect themselves.
    """
    parsed = urlparse(uri)
    params = parse_qs(parsed.query)

    sslmode = params.pop('sslmode', ['disable'])[0]
    connect_args: dict[str, Any] = {'ssl': sslmode not in ('disable', 'allow')}

    server_settings = {
        key: params.pop(key)[0]
        for key in _POSTGRES_SERVER_SETTINGS_PARAMS
        if key in params
    }
    if server_settings:
        connect_args['server_settings'] = server_settings

    scheme = parsed.scheme.split('+', 1)[0]
    driver_uri = urlunparse(
        parsed._replace(scheme=scheme, query=urlencode(params, doseq=True))
    )
    return driver_uri, connect_args


def init_async_db(
    db_uri: str,
    pool_size: int = 5,
) -> tuple[AsyncEngine, sessionmaker]:
    driver_uri, connect_args = build_asyncpg_connect_args(db_uri)
    parsed = urlparse(driver_uri)
    async_uri = urlunparse(parsed._replace(scheme='postgresql+asyncpg'))
    engine = create_async_engine(
        async_uri,
        pool_size=pool_size,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    factory = sessionmaker(  # type: ignore[type-var]
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, factory


@asynccontextmanager
async def async_session_scope(
    factory: sessionmaker,
) -> AsyncGenerator[AsyncSession, None]:
    session: AsyncSession = factory()
    token = _current_session.set(session)
    try:
        yield session
        await session.commit()
    except MissingGreenlet as exc:
        await session.rollback()
        raise RuntimeError(
            'Lazy loading triggered in async context. '
            'Use selectinload() to eager-load relationships in async DAO queries.'
        ) from exc
    except (Exception, CancelledError):
        await session.rollback()
        raise
    finally:
        await session.close()
        _current_session.reset(token)
