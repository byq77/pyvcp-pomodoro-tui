from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from .models import Base

APP_DIR_NAME = "pomodoro-tui"
SessionFactory = Callable[[], Session]


def default_data_dir() -> Path:
    xdg_data_home = Path.home() / ".local" / "share"
    app_dir = xdg_data_home / APP_DIR_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def default_db_path() -> Path:
    return default_data_dir() / "pomodoro.sqlite3"


def sqlite_url(db_path: Path | None = None) -> str:
    path = db_path or default_db_path()
    return f"sqlite+pysqlite:///{path}"


def create_engine_and_session_factory(
    db_path: Path | None = None, *, echo: bool = False
) -> tuple[Engine, SessionFactory]:
    engine = create_engine(sqlite_url(db_path), echo=echo, future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, factory


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
