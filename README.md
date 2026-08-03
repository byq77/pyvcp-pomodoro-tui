# Pomodoro TUI

Terminal Pomodoro application in Python using:

- asciimatics
- SQLite
- SQLAlchemy
- python-dotenv

This is a vibe-coded project.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .[dev] --config-settings editable_mode=strict
pomodoro-tui
```

Dependencies are managed in `requirements.txt` and loaded dynamically by `pyproject.toml`.

By default, data is stored in `~/.local/share/pomodoro-tui/pomodoro.sqlite3`.

Use a custom database path from the command line:

```bash
pomodoro-tui --db-path pomodoro.sqlite3
```

For local development or automation, the application also loads `.env` and uses `TEST_DB_PATH`
when `--db-path` is not provided:

```dotenv
TEST_DB_PATH=/tmp/pomodoro.sqlite3
```

## Controls

Global:

- `←` / `→` navigate the top menu
- `Enter` activate the highlighted menu item
- `Q` quit

Timer view:

- `Space` start / pause / resume
- `Tab` cycle session mode: Silent (`x1.5`), Normal (`x1.0`), Dirty (`x0.5`)
- `N` skip current phase
- `X` stop timer

Configuration view:

- `Up` / `Down` select setting
- `-` / `+` change numeric value
- `Space` toggle boolean value
- `S` save settings

## Features

- Full Pomodoro cycle with automatic phase transitions.
- Circular timer progress ring that fills clockwise as each phase elapses and encloses the session counter and progress legend.
- Persistent configuration in SQLite.
- Timer runtime state persists across app restarts until the day changes.
- History tracking for completed/interrupted phases.
- Session modes that adjust completed focus-session points: Silent (`x1.5`), Normal (`x1.0`),
  and Dirty (`x0.5`).
- Achievements view with milestone tracking for completed pomodoros and daily streaks.
- Optional achievements toggle in configuration.
- Daily focus streak boosts that increase completed focus-session points:
  - 4 in a row: `x1.5`
  - 8 in a row: `x2.0`
  - 12 in a row: `x3.0`
  - 16 in a row: `x4.0`
- Analytics snapshot:
  - daily totals
  - current streak
  - daily goal progress
