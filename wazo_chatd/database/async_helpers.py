# Copyright 2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


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
    )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


@asynccontextmanager
async def async_session_scope(
    factory: sessionmaker,
) -> AsyncGenerator[AsyncSession, None]:
    session: AsyncSession = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
