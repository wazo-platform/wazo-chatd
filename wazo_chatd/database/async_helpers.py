# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from asyncio import CancelledError
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

_current_session: ContextVar[AsyncSession] = ContextVar('_current_session')


def get_async_session() -> AsyncSession:
    return _current_session.get()


def make_async_uri(sync_uri: str) -> str:
    if '+asyncpg' in sync_uri:
        return sync_uri
    return sync_uri.replace('postgresql://', 'postgresql+asyncpg://', 1)


def parse_ssl_from_uri(uri: str) -> bool:
    """Extract sslmode from a PostgreSQL URI.

    Returns True if SSL is requested, False otherwise (default).
    asyncpg does not accept sslmode as a keyword argument through
    SQLAlchemy, so we parse it from the URI ourselves.
    """
    sslmode = parse_qs(urlparse(uri).query).get('sslmode', ['disable'])[0]
    return sslmode not in ('disable', 'allow')


def _strip_sslmode_from_uri(uri: str) -> str:
    """Remove sslmode from URI to avoid asyncpg keyword conflict."""
    parsed = urlparse(uri)
    params = parse_qs(parsed.query)
    params.pop('sslmode', None)
    return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))


def init_async_db(
    db_uri: str,
    pool_size: int = 5,
) -> tuple[AsyncEngine, sessionmaker]:
    ssl = parse_ssl_from_uri(db_uri)
    async_uri = make_async_uri(_strip_sslmode_from_uri(db_uri))
    engine = create_async_engine(
        async_uri,
        pool_size=pool_size,
        pool_pre_ping=True,
        connect_args={'ssl': ssl},
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
