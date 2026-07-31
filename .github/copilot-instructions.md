# Pomodoro TUI Copilot Instructions

## Workflow

- Read the relevant code first. Don't propose solutions before understanding the existing code.
- Never analyze Python virtual-environment directories (such as `.venv`) or Python build artifacts
(such as `build/`, `dist/`, and `*.egg-info/`). Restrict code analysis to source, tests, and other
repository-maintained files.
- When working in a git worktree, create and use a separate `.venv` in that worktree. Do not
reuse the virtual environment from the main checkout or another worktree. Never apply changes from a worktree to the main checkout or another worktree.

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

## Git

<!-- TODO: Add Git workflow instructions -->

## Linting and Formatting

Do it after editing code, before committing, and before pushing to the remote repository. The `ruff` tool is used for linting and formatting checks:

```bash
python -m ruff check src
python -m ruff format --check src
```

There is currently no test directory or test runner configuration, so no full-suite or single-test command exists. If tests are introduced, keep them under `tests/`; the existing Ruff configuration already provides test-specific rule exceptions.

## Architecture

- `pomodoro_tui.__main__` loads `.env`, parses `--db-path`, and falls back to `TEST_DB_PATH`. It
  constructs `PomodoroApplication`, which is then presented by `PomodoroTUI`.
- `PomodoroApplication` is the orchestration boundary. It initializes the database and services,
  owns the active `PomodoroTimer`, persists phase records, maintains the accumulated point total and
  UI status message, and saves or restores active timer state.
- `PomodoroTimer` is in-memory domain logic with no database or UI dependency. It advances active
  phases with `time.monotonic()`, returns `TimerPhaseRecord` values for completed or interrupted
  work, selects short or long breaks from the focus-cycle counter, and exports/imports
  `TimerRuntimeState`.
- `PomodoroTUI` is the asciimatics presentation layer. Its 0.1-second loop calls `app.tick()`,
  renders timer, configuration, and history modes, and maps input only to application methods. The
  `Screen.wrapper` retry loop owns resize recovery; drawing helpers must keep all output in bounds.
- SQLAlchemy models in `models.py` define `AppConfig`, `PomodoroSession`, and `AppTimerState`.
  `db.py` creates the SQLite engine, enables foreign keys on every connection, and initializes
  tables with `Base.metadata.create_all()`. The default database is
  `~/.local/share/pomodoro-tui/pomodoro.sqlite3`.
- `ConfigService` persists the singleton `AppConfig` row (`id=1`) and exposes detached
  `ConfigValues`. `HistoryService` stores phase records and derives history, totals, goals, streaks,
  and points. `RuntimeStateService` persists the singleton active timer state and discards it when
  it was saved on a prior local calendar day.

## Project Conventions

- Keep changes within the existing layers: the timer returns records and runtime-state values; the
  application persists and coordinates them; the UI calls application methods rather than services
  or timer internals.
- Store persisted timestamps as timezone-aware UTC datetimes. Use `time.monotonic()` exclusively to
  advance an in-process timer; never derive elapsed duration from wall-clock timestamps.
- Synchronize runtime state after every timer mutation and on shutdown. Clearing a stopped timer
  state is intentional; restoration is limited to state saved on the current local day.
- Preserve persisted table names and the values of `PhaseType` and `SessionStatus` enums. SQLite
  databases already store these SQLAlchemy enum-backed values.
- Save settings through `ConfigService.save()`, then apply them with
  `PomodoroTimer.apply_settings()`. The configuration UI edits a `dataclasses.replace()` draft and
  reports validation errors through `status_message`; do not mutate saved configuration fields
  directly from the UI.
- Use `@dataclass(slots=True)` for transient timer, configuration, history, and runtime-state value
  objects, consistent with the existing models.
- Account for terminal dimensions before every `screen.print_at` call, including centered text and
  dynamically sized timer rings. Keep keyboard controls and labels aligned with `README.md`.
- Follow the configured Ruff style: 99-character lines, Google docstrings when adding docstrings,
  and Ruff-managed import ordering. Use `from __future__ import annotations` and package-relative
  imports in package modules.
