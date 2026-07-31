# Pomodoro TUI Copilot Instructions

## Workflow

- Read the relevant code first. Don't propose solutions before understanding the existing code.
- Always run commands from the repository root.
- Never analyze Python virtual-environment directories (such as `.venv`) or Python build artifacts
(such as `build/`, `dist/`, and `*.egg-info/`). Restrict code analysis to source, tests, and other
repository-maintained files.
- When working in a git worktree, create and use a separate `.venv` in that worktree. Do not
reuse the virtual environment from the main checkout or another worktree.

## Build

Create an .venv environment (if not already created) and install the project in editable mode with development dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .[dev] --config-settings editable_mode=strict
```

## Run

Before running the application, ensure that the `.env` file exists in the root directory and contains a valid `TEST_DB_PATH` value:
```dotenv
TEST_DB_PATH=/tmp/pomodoro.sqlite3
```

Run the application in the terminal:
```bash
pomodoro-tui
```

You can also specify a database path directly with the `--db-path` option:
```bash
pomodoro-tui --db-path /tmp/pomodoro.sqlite3
```

Never run `pomodoro-tui` without the `--db-path` option or the `.env` file! We do not want to accidentally overwrite the default database in ~/.local/share/pomodoro-tui/pomodoro.sqlite3.

## Linting and Formatting

Do it after editing code, before committing, and before pushing to the remote repository. The `ruff` tool is used for linting and formatting checks:

```bash
python -m ruff check src
python -m ruff format --check src
```

There is currently no test directory or test runner configuration, so no full-suite or single-test command exists. If tests are introduced, keep them under `tests/`; the existing Ruff configuration already provides test-specific rule exceptions.

## Architecture

- `pomodoro_tui.__main__` loads `.env`, parses `--db-path`, and falls back to `TEST_DB_PATH` when
	no command-line database path is given. It creates `PomodoroApplication`, then starts
	`PomodoroTUI`.
- `PomodoroApplication` is the orchestration boundary: it creates the SQLite/SQLAlchemy services, owns the active `PomodoroTimer`, persists `TimerPhaseRecord` values returned by timer operations, and supplies status text to the UI.
- `PomodoroTimer` is in-memory domain logic. `tick()` advances elapsed time using `time.monotonic()` and returns completed phase records; `skip()` and `stop()` return interrupted records when elapsed work exists. It must not access the database or UI.
- `PomodoroTUI` is the asciimatics presentation layer. Its 0.1-second screen loop calls `app.tick()`, renders one of the timer/config/history modes, and maps keys to application methods. Handle terminal resize through the existing `Screen.wrapper` retry loop.
- SQLAlchemy models in `models.py` define both persistence schemas. `db.py` creates the engine, enables SQLite foreign keys on each connection, and initializes tables with `Base.metadata.create_all()`. By default, the database is `~/.local/share/pomodoro-tui/pomodoro.sqlite3`.
- `ConfigService` persists one `AppConfig` row with `id=1`; `ConfigValues` is the detached, editable representation used by the UI. `HistoryService` derives recent sessions, daily totals, goals, and streaks from persisted session records.

## Project Conventions

- Keep domain changes flowing through the existing layers: timer returns records, application persists them through `HistoryService`, and UI calls application methods rather than services or the timer directly.
- Store session timestamps as timezone-aware UTC datetimes. Use `time.monotonic()` only for elapsed timer progression; do not compute elapsed durations from wall-clock time.
- Preserve `PhaseType` and `SessionStatus` enum values when changing persistence behavior because SQLAlchemy stores these enum-backed values in existing SQLite databases.
- Apply settings through `ConfigService.save()` and `PomodoroTimer.apply_settings()`. The configuration screen deliberately edits a `dataclasses.replace()` draft and exposes validation errors in `status_message`, rather than mutating saved configuration field by field.
- Model transient timer/config/history value objects as `@dataclass(slots=True)`, matching the existing `TimerSettings`, snapshots, records, and configuration values.
- UI drawing must account for terminal dimensions before calling `screen.print_at`; keep controls and rendered text consistent with the documented keyboard mappings.
- Follow the configured Ruff style: 99-character lines, Google docstring convention when docstrings are added, and Ruff-managed import ordering. Use `from __future__ import annotations` and package-relative imports as in the existing modules.
