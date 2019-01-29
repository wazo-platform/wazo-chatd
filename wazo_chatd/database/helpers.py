# Copyright 2019 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

from contextlib import contextmanager
from functools import wraps

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session


Session = scoped_session(sessionmaker())


def init_db(db_uri):
    engine = create_engine(db_uri)
    Session.configure(bind=engine)


def daosession(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        session = Session()
        return func(session, *args, **kwargs)
    return wrapped


@daosession
def get_dao_session(session):
    return session


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
