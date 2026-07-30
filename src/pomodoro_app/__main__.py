from __future__ import annotations
import argparse
from pathlib import Path
from .app import PomodoroApplication
from .ui.tui import PomodoroTUI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pomodoro terminal timer")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
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
