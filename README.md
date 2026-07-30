# Pomodoro TUI

Terminal Pomodoro application in Python using:
- asciimatics
- SQLite
- SQLAlchemy
- python-dotenv

This is a vibe-coded project.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
pomodoro-tui
```

Dependencies are managed in `requirements.txt` and loaded dynamically by `pyproject.toml`.

By default, data is stored in `~/.local/share/pomodoro-app/pomodoro.sqlite3`.

Use a custom database path from the command line:

```bash
pomodoro-tui --db-path /path/to/pomodoro.sqlite3
```

For local development or automation, the application also loads `.env` and uses `TEST_DB_PATH`
when `--db-path` is not provided:

```dotenv
TEST_DB_PATH=/tmp/pomodoro.sqlite3
```

## Controls

Global:
- `T` timer view
- `C` configuration view
- `H` history view
- `Q` quit

Timer view:
- `Space` start / pause / resume
- `N` skip current phase
- `X` stop timer

Configuration view:
- `Up` / `Down` select setting
- `Left` / `Right` or `-` / `+` change numeric value
- `Space` toggle boolean value
- `S` save settings

## Features

- Full Pomodoro cycle with automatic phase transitions.
- Circular timer progress ring that fills clockwise as each phase elapses and encloses the session counter and progress legend.
- Persistent configuration in SQLite.
- History tracking for completed/interrupted phases.
- Analytics snapshot:
  - daily totals
  - current streak
  - daily goal progress
