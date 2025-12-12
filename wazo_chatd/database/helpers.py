# Copyright 2019-2025 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, TypeVar

from sqlalchemy import create_engine
from sqlalchemy.orm import Query, scoped_session, sessionmaker

if TYPE_CHECKING:
    # NOTE(clanglois): can be removed in sqlalchemy 2.0
    from sqlalchemy_stubs import Query  # type: ignore[no-redef] # noqa: F811

    T = TypeVar('T')


Session = scoped_session(sessionmaker())


def init_db(db_uri, echo=False, pool_size=16):
    engine = create_engine(db_uri, echo=echo, pool_size=pool_size, pool_pre_ping=True)
    Session.configure(bind=engine)


@contextmanager
def session_scope():
    session = Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        Session.remove()


def get_query_main_entity(query: Query[T]) -> T:
    """
    Returns the main target entity of the query,
    given it may change while building the query (e.g. aliased)
    """
    assert query.column_descriptions
    return query.column_descriptions[0]['entity']
