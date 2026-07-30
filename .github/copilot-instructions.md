# Pomodoro TUI Copilot Instructions

## Commands

Run commands from the repository root.

When working in a Git worktree, create and use a separate `.venv` in that worktree. Do not
reuse the virtual environment from the main checkout or another worktree.

```bash
# Set up and run
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
pomodoro-tui

# Run against an isolated SQLite database (useful for manual verification)
pomodoro-tui --db-path /tmp/pomodoro.sqlite3

# Or configure the default database path for local development or automation
echo 'TEST_DB_PATH=/tmp/pomodoro.sqlite3' > .env
pomodoro-tui

# Lint and format check
# Ruff is configured in pyproject.toml but is not a project dependency.
python -m pip install ruff
python -m ruff check src
python -m ruff format --check src
```

Never run `pomodoro-tui` without the `--db-path` option or the `.env` file! We do not want to accidentally overwrite the default database in ~/.local/share/pomodoro-app/pomodoro.sqlite3.

There is currently no test directory or test runner configuration, so no full-suite or single-test command exists. If tests are introduced, keep them under `tests/`; the existing Ruff configuration already provides test-specific rule exceptions.

## Architecture

- `pomodoro_tui.__main__` loads `.env`, parses `--db-path`, and falls back to `TEST_DB_PATH` when
	no command-line database path is given. It creates `PomodoroApplication`, then starts
	`PomodoroTUI`.
- `PomodoroApplication` is the orchestration boundary: it creates the SQLite/SQLAlchemy services, owns the active `PomodoroTimer`, persists `TimerPhaseRecord` values returned by timer operations, and supplies status text to the UI.
- `PomodoroTimer` is in-memory domain logic. `tick()` advances elapsed time using `time.monotonic()` and returns completed phase records; `skip()` and `stop()` return interrupted records when elapsed work exists. It must not access the database or UI.
- `PomodoroTUI` is the asciimatics presentation layer. Its 0.1-second screen loop calls `app.tick()`, renders one of the timer/config/history modes, and maps keys to application methods. Handle terminal resize through the existing `Screen.wrapper` retry loop.
- SQLAlchemy models in `models.py` define both persistence schemas. `db.py` creates the engine, enables SQLite foreign keys on each connection, and initializes tables with `Base.metadata.create_all()`. By default, the database is `~/.local/share/pomodoro-app/pomodoro.sqlite3`.
- `ConfigService` persists one `AppConfig` row with `id=1`; `ConfigValues` is the detached, editable representation used by the UI. `HistoryService` derives recent sessions, daily totals, goals, and streaks from persisted session records.

## Project Conventions

- Keep domain changes flowing through the existing layers: timer returns records, application persists them through `HistoryService`, and UI calls application methods rather than services or the timer directly.
- Store session timestamps as timezone-aware UTC datetimes. Use `time.monotonic()` only for elapsed timer progression; do not compute elapsed durations from wall-clock time.
- Preserve `PhaseType` and `SessionStatus` enum values when changing persistence behavior because SQLAlchemy stores these enum-backed values in existing SQLite databases.
- Apply settings through `ConfigService.save()` and `PomodoroTimer.apply_settings()`. The configuration screen deliberately edits a `dataclasses.replace()` draft and exposes validation errors in `status_message`, rather than mutating saved configuration field by field.
- Model transient timer/config/history value objects as `@dataclass(slots=True)`, matching the existing `TimerSettings`, snapshots, records, and configuration values.
- UI drawing must account for terminal dimensions before calling `screen.print_at`; keep controls and rendered text consistent with the documented keyboard mappings.
- Follow the configured Ruff style: 99-character lines, Google docstring convention when docstrings are added, and Ruff-managed import ordering. Use `from __future__ import annotations` and package-relative imports as in the existing modules.
