from __future__ import annotations
import argparse
import os
from pathlib import Path
import dotenv
from . import __version__
from .app import PomodoroApplication
from .ui.tui import PomodoroTUI

dotenv.load_dotenv()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pomodoro-tui", description="Pomodoro terminal timer")
    default_db_path_env = os.getenv("TEST_DB_PATH")
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(default_db_path_env) if default_db_path_env else None,
        help="Optional path to SQLite database file",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = PomodoroApplication(db_path=args.db_path)
    ui = PomodoroTUI(app)
    ui.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
