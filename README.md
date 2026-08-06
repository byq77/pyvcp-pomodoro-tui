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
- `Up` / `Down` increase or decrease the focus-session counter (never below `0`)
- `Tab` cycle session mode: Silent (`x1.5`), Normal (`x1.0`), Dirty (`x0.5`)
- `N` skip current phase
- `X` stop timer

Configuration view:

- `Up` / `Down` select setting
- `-` / `+` change numeric value
- `Space` toggle boolean value
- `S` save settings

Rewards view:

- `Up` / `Down` select a reward
- `N` create a new reward (opens a form for name and cost)
- `E` edit the selected reward's name and cost
- `D` delete the selected reward (asks for confirmation)
- `B` buy the selected reward (opens a form to choose quantity)

Debt view:

- `Up` / `Down` select a debt entry
- `N` add a new debt entry (opens a form for description and amount)
- `E` edit the selected debt entry's description and amount
- `D` delete the selected debt entry (asks for confirmation)
- `P` pay off debt with points (opens a form to choose the amount)

## Features

- Full Pomodoro cycle with automatic phase transitions.
- Non-blocking audio alert when a focus or break phase completes.
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
  - total points spent on rewards and total rewards acquired
- Rewards screen for spending points on user-defined prizes:
  - create, rename, re-price, and delete rewards using asciimatics forms
  - buy a chosen quantity of a reward if enough points are available
  - the `Points:` total shown across the app is the available balance
    (points earned minus points spent on rewards and paid off as debt)
  - each purchase keeps a frozen snapshot of the reward's name and cost, so
    editing or deleting a reward never changes past purchase history
- Debt screen for tracking and paying down owed amounts with points:
  - add, edit, and delete one-off debt entries (description and amount) using
    asciimatics forms
  - pay off outstanding debt with available points (1 point = 1 unit of debt);
    a payment is capped to the remaining debt, and is rejected if it would
    exceed the available points balance
  - total debt is the sum of debt entries minus total payments made, clamped
    at a minimum of 0
  - all debt entries and payments are recorded and shown on the screen
