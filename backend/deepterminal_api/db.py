from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True, future=True)


@lru_cache
def session_factory():
    return sessionmaker(bind=engine(), expire_on_commit=False)


def get_db():
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db: Session = session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
