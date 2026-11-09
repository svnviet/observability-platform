from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import database_url


class Database:
    def __init__(self, url: str) -> None:
        kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, pool_pre_ping=True, **kwargs)
        self._factory = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self._factory()


@lru_cache(maxsize=1)
def get_database() -> Database:
    return Database(database_url())


def get_session() -> Iterator[Session]:
    session = get_database().session()
    try:
        yield session
    finally:
        session.close()
