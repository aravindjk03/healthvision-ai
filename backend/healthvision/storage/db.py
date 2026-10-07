"""Database setup: SQLite (WAL, foreign keys) + schema creation + audit-log protection triggers."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from .orm import Base

SCHEMA_REVISION = "0001_initial"

_TRIGGERS = [
    """CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_logs
       BEGIN SELECT RAISE(ABORT, 'audit_logs is append-only'); END""",
    """CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_logs
       WHEN COALESCE((SELECT value FROM _app_flags WHERE name = 'audit_purge'), 0) != 1
       BEGIN SELECT RAISE(ABORT, 'audit_logs rows may only be removed by the retention purge'); END""",
]


class Database:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(self.engine, "connect")
        def _pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()

        self._factory = sessionmaker(self.engine, expire_on_commit=False)

    def migrate(self) -> None:
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as conn:
            for ddl in _TRIGGERS:
                conn.execute(text(ddl))
            conn.execute(text("CREATE TABLE IF NOT EXISTS _schema_revision (revision TEXT PRIMARY KEY)"))
            conn.execute(text("INSERT OR IGNORE INTO _schema_revision (revision) VALUES (:r)"), {"r": SCHEMA_REVISION})

    @contextmanager
    def session(self):
        s: Session = self._factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()
