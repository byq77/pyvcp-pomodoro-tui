from __future__ import annotations
import math
import time
from dataclasses import replace
from asciimatics.exceptions import ResizeScreenError
from asciimatics.screen import Screen
from ..app import PomodoroApplication
from ..models import SessionStatus

LARGE_DIGITS = {
    "0": (" ### ", "#   #", "#   #", "#   #", " ### "),
    "1": ("  #  ", " ##  ", "  #  ", "  #  ", " ### "),
    "2": (" ### ", "#   #", "   # ", "  #  ", "#####"),
    "3": ("#### ", "    #", " ### ", "    #", "#### "),
    "4": ("#   #", "#   #", "#####", "    #", "    #"),
    "5": ("#####", "#    ", "#### ", "    #", "#### "),
    "6": (" ### ", "#    ", "#### ", "#   #", " ### "),
    "7": ("#####", "    #", "   # ", "  #  ", "  #  "),
    "8": (" ### ", "#   #", " ### ", "#   #", " ### "),
    "9": (" ### ", "#   #", " ####", "    #", " ### "),
    ":": ("     ", "  #  ", "     ", "  #  ", "     "),
}

PROGRESS_RING_STEPS = 48
PROGRESS_RING_RADIUS_X = 28
PROGRESS_RING_RADIUS_Y = 9


def _format_seconds(total_seconds: int) -> str:
    minutes, seconds = divmod(max(0, total_seconds), 60)
    return f"{minutes:02d}:{seconds:02d}"


def _progress_ring_points() -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    for step in range(PROGRESS_RING_STEPS):
        angle = (2 * math.pi * step / PROGRESS_RING_STEPS) - (math.pi / 2)
        point = (
            round(PROGRESS_RING_RADIUS_X * math.cos(angle)),
            round(PROGRESS_RING_RADIUS_Y * math.sin(angle)),
        )
        if point not in points:
            points.append(point)
    return points


PROGRESS_RING_POINTS = _progress_ring_points()


class PomodoroTUI:
    def __init__(self, app: PomodoroApplication):
        self._app = app
        self._mode = "timer"
        self._running = True
        self._config_draft = app.build_config_draft()
        self._config_fields: list[tuple[str, str, str]] = [
            ("focus_duration_min", "Focus duration (min)", "int"),
            ("short_break_duration_min", "Short break duration (min)", "int"),
            ("long_break_duration_min", "Long break duration (min)", "int"),
            ("long_break_interval", "Long break every N focus sessions", "int"),
            ("daily_goal_sessions", "Daily goal (focus sessions)", "int"),
            ("history_days_visible", "History days shown", "int"),
            ("auto_start_next_phase", "Auto-start next phase", "bool"),
            ("include_breaks_in_totals", "Include breaks in totals", "bool"),
            ("streak_requires_goal", "Streak requires meeting daily goal", "bool"),
            ("track_weekends", "Track weekends in streaks", "bool"),
        ]
        self._selected_config_index = 0

    def run(self) -> None:
        while True:
            try:
                Screen.wrapper(self._screen_loop, catch_interrupt=True)
                return
            except ResizeScreenError:
                continue

    def _screen_loop(self, screen: Screen) -> None:
        self._running = True
        screen.clear()
        while self._running:
            if screen.has_resized():
                raise ResizeScreenError("Terminal resized")
            self._app.tick()
            screen.clear_buffer(
                Screen.COLOUR_WHITE,
                Screen.A_NORMAL,
                Screen.COLOUR_BLACK,
            )
            self._draw_header(screen)
            if self._mode == "timer":
                self._draw_timer(screen)
            elif self._mode == "config":
                self._draw_config(screen)
            else:
                self._draw_history(screen)
            screen.refresh()
            self._handle_key(screen.get_key())
            if screen.has_resized():
                raise ResizeScreenError("Terminal resized")
            time.sleep(0.1)

    def _draw_header(self, screen: Screen) -> None:
        title = "Pomodoro TUI  |  [T]imer [C]onfig [H]istory [Q]uit"
        screen.print_at(title, 0, 0, Screen.COLOUR_CYAN, Screen.A_BOLD)
        screen.print_at("-" * screen.width, 0, 1)

    def _draw_timer(self, screen: Screen) -> None:
        snapshot = self._app.timer.snapshot()
        phase_name = snapshot.phase.value.replace("_", " ").title()
        state = "Running" if snapshot.running else "Paused" if snapshot.paused else "Stopped"
        self._draw_phase_tabs(screen, snapshot.phase.value)

        timer_lines = self._large_timer_lines(_format_seconds(snapshot.seconds_remaining))
        timer_top = max(8, (screen.height - len(timer_lines)) // 2 - 2)
        ring_center_y = timer_top + 4
        self._draw_progress_ring(
            screen,
            ring_center_y,
            self._phase_progress(snapshot.seconds_remaining, snapshot.phase_duration_seconds),
        )
        for offset, line in enumerate(timer_lines):
            self._print_centered(
                screen, line, timer_top + offset, Screen.COLOUR_GREEN, Screen.A_BOLD
            )

        action = "PAUSE" if snapshot.running else "RESUME" if snapshot.paused else "START"
        self._print_centered(
            screen,
            f"[ {action} ]",
            ring_center_y + 6,
            Screen.COLOUR_CYAN,
            Screen.A_BOLD,
        )
        self._print_centered(screen, f"{phase_name}  |  {state}", ring_center_y - 6)
        self._print_centered(
            screen,
            f"Focus sessions: {snapshot.focus_sessions_completed_in_cycle}",
            ring_center_y + 2,
        )
        self._print_centered(
            screen,
            "# elapsed  . remaining",
            ring_center_y + 4,
        )
        self._print_centered(
            screen,
            "Space: start/pause/resume   N: skip   X: stop",
            min(screen.height - 2, timer_top + len(timer_lines) + 6),
        )
        self._print_centered(
            screen,
            self._app.status_message,
            screen.height - 1,
            Screen.COLOUR_YELLOW,
        )

    @staticmethod
    def _large_timer_lines(value: str) -> list[str]:
        return [" ".join(LARGE_DIGITS[character][row] for character in value) for row in range(5)]

    @staticmethod
    def _phase_progress(seconds_remaining: int, phase_duration_seconds: int) -> float:
        if phase_duration_seconds <= 0:
            return 0.0
        return min(1.0, max(0.0, 1 - (seconds_remaining / phase_duration_seconds)))

    @staticmethod
    def _draw_progress_ring(screen: Screen, center_y: int, progress: float) -> None:
        center_x = screen.width // 2
        filled_points = math.ceil(progress * len(PROGRESS_RING_POINTS))
        for index, (offset_x, offset_y) in enumerate(PROGRESS_RING_POINTS):
            x = center_x + offset_x
            y = center_y + offset_y
            if not (0 <= x < screen.width and 2 <= y < screen.height):
                continue
            if index < filled_points:
                screen.print_at("#", x, y, Screen.COLOUR_CYAN, Screen.A_BOLD)
            else:
                screen.print_at(".", x, y, Screen.COLOUR_WHITE)

    def _draw_phase_tabs(self, screen: Screen, current_phase: str) -> None:
        tabs = []
        for phase, label in (
            ("focus", "Pomodoro"),
            ("short_break", "Short Break"),
            ("long_break", "Long Break"),
        ):
            tabs.append(f"[{label}]" if phase == current_phase else f" {label} ")
        self._print_centered(screen, "  ".join(tabs), 2, Screen.COLOUR_WHITE, Screen.A_BOLD)

    @staticmethod
    def _print_centered(
        screen: Screen,
        text: str,
        y: int,
        colour: int = Screen.COLOUR_WHITE,
        attr: int = Screen.A_NORMAL,
    ) -> None:
        screen.print_at(text, max(0, (screen.width - len(text)) // 2), y, colour, attr)

    def _draw_config(self, screen: Screen) -> None:
        screen.print_at("Mode: Configuration", 0, 3, Screen.COLOUR_WHITE, Screen.A_BOLD)
        screen.print_at(
            "Controls: [Up/Down]=select [Left/Right or +/-]=change [Space]=toggle [S]=save",
            0,
            4,
        )
        line = 6
        for idx, (field_name, label, field_type) in enumerate(self._config_fields):
            value = getattr(self._config_draft, field_name)
            pointer = ">" if idx == self._selected_config_index else " "
            colour = (
                Screen.COLOUR_CYAN if idx == self._selected_config_index else Screen.COLOUR_WHITE
            )
            rendered_value = (
                "on"
                if field_type == "bool" and value
                else "off"
                if field_type == "bool"
                else str(value)
            )
            screen.print_at(f"{pointer} {label}: {rendered_value}", 0, line, colour)
            line += 1
        screen.print_at(f"Status: {self._app.status_message}", 0, line + 1, Screen.COLOUR_YELLOW)

    def _draw_history(self, screen: Screen) -> None:
        snapshot = self._app.history_snapshot()
        screen.print_at("Mode: History", 0, 3, Screen.COLOUR_WHITE, Screen.A_BOLD)
        goal = snapshot.goal_progress_today
        ratio = min(100, int(goal.completion_ratio * 100))
        screen.print_at(
            f"Today goal progress: {goal.completed_focus_sessions}/{goal.goal_sessions} ({ratio}%)",
            0,
            5,
            Screen.COLOUR_GREEN,
        )
        screen.print_at(f"Current streak: {snapshot.current_streak_days} day(s)", 0, 6)
        screen.print_at("Recent sessions:", 0, 8, Screen.COLOUR_CYAN, Screen.A_BOLD)

        line = 9
        for row in snapshot.recent_sessions[: min(10, screen.height - 14)]:
            if line >= screen.height - 3:
                break
            stamp = row.started_at.astimezone().strftime("%Y-%m-%d %H:%M")
            status = "ok" if row.status == SessionStatus.COMPLETED else "interrupted"
            phase = row.phase_type.value.replace("_", " ")
            duration = _format_seconds(row.actual_duration_seconds)
            screen.print_at(f"{stamp} | {phase:<11} | {status:<11} | {duration}", 0, line)
            line += 1

        line += 1
        if line < screen.height - 1:
            screen.print_at(
                "Daily totals (latest first):", 0, line, Screen.COLOUR_CYAN, Screen.A_BOLD
            )
            line += 1
        for day in snapshot.daily_totals[: min(5, max(0, screen.height - line - 2))]:
            if line >= screen.height - 1:
                break
            total_minutes = day.total_seconds // 60
            screen.print_at(
                f"{day.day.isoformat()} | completed={day.completed_sessions} "
                f"| focus={day.completed_focus_sessions} | minutes={total_minutes}",
                0,
                line,
            )
            line += 1
        if line < screen.height:
            screen.print_at(
                f"Status: {self._app.status_message}",
                0,
                min(screen.height - 1, line + 1),
                Screen.COLOUR_YELLOW,
            )

    def _handle_key(self, key: int | None) -> None:
        if key is None:
            return
        if key in (ord("q"), ord("Q")):
            if self._app.timer.snapshot().running or self._app.timer.snapshot().paused:
                self._app.stop_timer(reason="quit")
            self._running = False
            return
        if key in (ord("t"), ord("T")):
            self._mode = "timer"
            return
        if key in (ord("c"), ord("C")):
            self._mode = "config"
            self._config_draft = replace(self._app.config)
            return
        if key in (ord("h"), ord("H")):
            self._mode = "history"
            return

        if self._mode == "timer":
            self._handle_timer_key(key)
        elif self._mode == "config":
            self._handle_config_key(key)

    def _handle_timer_key(self, key: int) -> None:
        if key == ord(" "):
            self._app.toggle_timer()
        elif key in (ord("n"), ord("N")):
            self._app.skip_phase()
        elif key in (ord("x"), ord("X")):
            self._app.stop_timer(reason="stopped")

    def _handle_config_key(self, key: int) -> None:
        if key == Screen.KEY_UP:
            self._selected_config_index = max(0, self._selected_config_index - 1)
            return
        if key == Screen.KEY_DOWN:
            self._selected_config_index = min(
                len(self._config_fields) - 1, self._selected_config_index + 1
            )
            return
        if key in (ord("s"), ord("S")):
            try:
                self._app.save_config(self._config_draft)
            except ValueError as exc:
                self._app.status_message = f"Config error: {exc}"
            return

        field_name, _label, field_type = self._config_fields[self._selected_config_index]
        if field_type == "bool":
            if key == ord(" "):
                setattr(
                    self._config_draft, field_name, not getattr(self._config_draft, field_name)
                )
            return

        if key in (Screen.KEY_LEFT, ord("-")):
            setattr(
                self._config_draft,
                field_name,
                max(1, int(getattr(self._config_draft, field_name)) - 1),
            )
        elif key in (Screen.KEY_RIGHT, ord("+"), ord("=")):
            setattr(
                self._config_draft,
                field_name,
                int(getattr(self._config_draft, field_name)) + 1,
            )
