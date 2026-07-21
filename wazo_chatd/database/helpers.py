# Copyright 2019-2026 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, TypeVar

from sqlalchemy import column, create_engine, update, values
from sqlalchemy.orm import Query
from sqlalchemy.orm import Session as SASession
from sqlalchemy.orm import scoped_session, sessionmaker

if TYPE_CHECKING:
    # NOTE(clanglois): can be removed in sqlalchemy 2.0
    from sqlalchemy_stubs import Query  # type: ignore[no-redef] # noqa: F811

    T = TypeVar('T')


Session = scoped_session(sessionmaker())

BULK_BATCH_SIZE = 1000


def _chunked(items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


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


def bulk_insert(session: SASession, instances: Sequence[Any]) -> None:
    for chunk in _chunked(instances, BULK_BATCH_SIZE):
        session.bulk_save_objects(chunk)
    session.flush()


def bulk_update(
    session: SASession,
    model: type[Any],
    columns: Sequence[tuple[str, Any]],
    rows: Sequence[tuple[Any, ...]],
    key_columns: Sequence[str],
) -> None:
    for chunk in _chunked(rows, BULK_BATCH_SIZE):
        source = values(
            *(column(name, type_) for name, type_ in columns),
            name='new_values',
        ).data(chunk)

        new_values = {
            name: source.c[name] for name, _ in columns if name not in key_columns
        }
        query = update(model).values(new_values)

        for key_column in key_columns:
            query = query.where(getattr(model, key_column) == source.c[key_column])

        query = query.execution_options(synchronize_session=False)
        session.execute(query)
    session.flush()


def bulk_delete(
    session: SASession, model: type[Any], in_target: Any, items: Sequence[Any]
) -> None:
    for chunk in _chunked(items, BULK_BATCH_SIZE):
        session.query(model).filter(in_target.in_(chunk)).delete(
            synchronize_session=False
        )
    session.flush()


def get_query_main_entity(query: Query[T]) -> T:
    """
    Returns the main target entity of the query,
    given it may change while building the query (e.g. aliased)
    """
    assert query.column_descriptions
    return query.column_descriptions[0]['entity']
