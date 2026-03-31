# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

_current_session: ContextVar[AsyncSession] = ContextVar('_current_session')


def get_async_session() -> AsyncSession:
    return _current_session.get()


def make_async_uri(sync_uri: str) -> str:
    if '+asyncpg' in sync_uri:
        return sync_uri
    return sync_uri.replace('postgresql://', 'postgresql+asyncpg://', 1)


def init_async_db(
    db_uri: str,
    pool_size: int = 5,
) -> tuple[AsyncEngine, sessionmaker]:
    async_uri = make_async_uri(db_uri)
    engine = create_async_engine(
        async_uri,
        pool_size=pool_size,
        pool_pre_ping=True,
        connect_args={'ssl': False},
    )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
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
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
        _current_session.reset(token)
