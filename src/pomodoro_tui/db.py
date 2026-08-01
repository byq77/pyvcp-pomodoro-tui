from __future__ import annotations
from collections.abc import Callable
from pathlib import Path
from sqlalchemy import Engine, create_engine, event, inspect, text
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
    _migrate_session_mode_columns(engine)
    _migrate_achievements_enabled_column(engine)


def _migrate_session_mode_columns(engine: Engine) -> None:
    """Add session-mode columns to databases created before session modes existed."""
    inspector = inspect(engine)
    columns_by_table = {
        table_name: {column["name"] for column in inspector.get_columns(table_name)}
        for table_name in ("pomodoro_session", "app_timer_state")
    }
    statements = {
        "pomodoro_session": (
            "ALTER TABLE pomodoro_session "
            "ADD COLUMN session_mode VARCHAR(6) NOT NULL DEFAULT 'normal'"
        ),
        "app_timer_state": (
            "ALTER TABLE app_timer_state "
            "ADD COLUMN session_mode VARCHAR(6) NOT NULL DEFAULT 'normal'"
        ),
    }
    with engine.begin() as connection:
        for table_name, statement in statements.items():
            if "session_mode" not in columns_by_table[table_name]:
                connection.execute(text(statement))


def _migrate_achievements_enabled_column(engine: Engine) -> None:
    """Add the achievements setting to databases created before it existed."""
    inspector = inspect(engine)
    app_config_columns = {column["name"] for column in inspector.get_columns("app_config")}
    if "achievements_enabled" in app_config_columns:
        return
    statement = "ALTER TABLE app_config ADD COLUMN achievements_enabled BOOLEAN NOT NULL DEFAULT 1"
    with engine.begin() as connection:
        connection.execute(text(statement))
