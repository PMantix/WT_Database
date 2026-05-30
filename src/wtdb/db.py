"""Engine, session factory, and DB lifecycle helpers.

SQLite is configured for the read-heavy, single-author workload described in the
plan: WAL journaling and enforced foreign keys, applied on every connection via
a ``connect`` event listener (PRAGMAs are per-connection in SQLite).
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import DB_URL, ensure_dirs
from .models import Base

engine: Engine = create_engine(DB_URL, future=True)
SessionLocal = sessionmaker(bind=engine, future=True, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _record) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


def init_db() -> None:
    """Create the database file and all tables if they don't exist."""
    ensure_dirs()
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()


def load_dataframe() -> pd.DataFrame:
    """Return the full aircraft table as a DataFrame for the app layer."""
    with engine.connect() as conn:
        return pd.read_sql_table("aircraft", conn)
