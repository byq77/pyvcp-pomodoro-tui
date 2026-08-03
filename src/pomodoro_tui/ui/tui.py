from __future__ import annotations
import math
import time
from dataclasses import replace
from functools import cache
from typing import TYPE_CHECKING
from asciimatics.exceptions import ResizeScreenError
from asciimatics.screen import Screen
from pomodoro_tui import __version__
from pomodoro_tui.models import SessionStatus

if TYPE_CHECKING:
    from pomodoro_tui.app import PomodoroApplication

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

PROGRESS_RING_STEPS = 96
# Terminal character cells are roughly twice as tall as they are wide, so the
# horizontal radius must be doubled relative to the vertical radius for the
# ring to read as a circle instead of a flattened ellipse.
PROGRESS_RING_ASPECT_RATIO = 2.0
# Vertical radii (in rows) for the three concentric rings, built outward from
# the innermost border. The inner radius must be large enough that the timer
# digits, phase label, and session count printed at its centre never touch
# it; the progress ring and outer border sit a fixed gap further out so
# neither border overlaps the coloured progress ring between them. The inner
# radius scales with the available terminal height (between these bounds) so
# the ring is as large as possible without pushing the surrounding text off
# screen on short terminals.
PROGRESS_RING_GAP_Y = 2
PROGRESS_RING_MIN_INNER_RADIUS_Y = 5
PROGRESS_RING_MAX_INNER_RADIUS_Y = 10
PROGRESS_RING_ELAPSED_GLYPH = "$$"


def _format_seconds(total_seconds: int) -> str:
    minutes, seconds = divmod(max(0, total_seconds), 60)
    return f"{minutes:02d}:{seconds:02d}"


def _ring_inner_radius(screen_height: int) -> int:
    """Pick the inner ring radius that best fits the available screen height.

    Reserves 3 rows above the ring for the header/tabs and 11 rows below it
    for the session readout, action button, legend, controls hint, and status
    line, then
    grows the ring to fill whatever height remains, clamped between
    ``PROGRESS_RING_MIN_INNER_RADIUS_Y`` and ``PROGRESS_RING_MAX_INNER_RADIUS_Y``.
    """
    overhead = 3 + 11 + 4 * PROGRESS_RING_GAP_Y
    available = (screen_height - overhead) // 2
    return max(PROGRESS_RING_MIN_INNER_RADIUS_Y, min(PROGRESS_RING_MAX_INNER_RADIUS_Y, available))


def _ring_radii(screen_height: int) -> tuple[int, int, int]:
    """Return the (inner, progress, outer) vertical radii for a given screen height."""
    inner = _ring_inner_radius(screen_height)
    mid = inner + PROGRESS_RING_GAP_Y
    outer = mid + PROGRESS_RING_GAP_Y
    return inner, mid, outer


@cache
def _circle_points(radius_y: int) -> tuple[tuple[int, int], ...]:
    """Build a set of (x, y) offsets tracing a circle of the given vertical radius.

    The horizontal radius is derived from ``radius_y`` using
    ``PROGRESS_RING_ASPECT_RATIO`` so the result renders as a circle rather
    than an ellipse on a terminal grid.
    """
    radius_x = round(radius_y * PROGRESS_RING_ASPECT_RATIO)
    points: list[tuple[int, int]] = []
    for step in range(PROGRESS_RING_STEPS):
        angle = (2 * math.pi * step / PROGRESS_RING_STEPS) - (math.pi / 2)
        point = (round(radius_x * math.cos(angle)), round(radius_y * math.sin(angle)))
        if point not in points:
            points.append(point)
    return tuple(points)


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
            ("achievements_enabled", "Enable achievements", "bool"),
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
            elif self._mode == "history":
                self._draw_history(screen)
            else:
                self._draw_achievements(screen)
            screen.refresh()
            self._handle_key(screen.get_key())
            if screen.has_resized():
                raise ResizeScreenError("Terminal resized")
            time.sleep(0.1)

    def _draw_header(self, screen: Screen) -> None:
        title = f"Pomodoro TUI v{__version__}  |  [T]imer [C]onfig [H]istory [A]chievements [Q]uit"
        screen.print_at(title, 0, 0, Screen.COLOUR_CYAN, Screen.A_BOLD)
        screen.print_at("-" * screen.width, 0, 1)

    def _draw_timer(self, screen: Screen) -> None:
        snapshot = self._app.timer.snapshot()
        phase_name = snapshot.phase.value.replace("_", " ").title()
        state = "Running" if snapshot.running else "Paused" if snapshot.paused else "Stopped"
        self._draw_phase_tabs(screen, snapshot.phase.value)

        _inner_radius, _mid_radius, outer_radius = _ring_radii(screen.height)
        timer_lines = self._large_timer_lines(_format_seconds(snapshot.seconds_remaining))
        # Reserve enough clearance above the ring for its outer border so the
        # phase tabs never collide with it, then centre the remaining content.
        min_top = outer_radius - 1
        timer_top = max(min_top, (screen.height - len(timer_lines)) // 2 - 2)
        ring_center_y = timer_top + len(timer_lines) // 2
        self._draw_progress_ring(
            screen,
            ring_center_y,
            self._phase_progress(snapshot.seconds_remaining, snapshot.phase_duration_seconds),
        )
        # Only the compact readout (phase/state, digits, session count) is
        # drawn inside the ring; it fits well within the inner border.
        self._print_centered(screen, f"{phase_name}  |  {state}", ring_center_y - 6)
        for offset, line in enumerate(timer_lines):
            self._print_centered(
                screen, line, timer_top + offset, Screen.COLOUR_GREEN, Screen.A_BOLD
            )
        self._print_centered(
            screen,
            f"Focus sessions: {snapshot.focus_sessions_completed_in_cycle}",
            timer_top + len(timer_lines) + 1,
        )

        # Everything below is printed outside the outer border so long lines
        # of text never overlap the ring. Rows are clamped from the bottom up
        # so that on short terminals each line still gets its own row instead
        # of collapsing onto the one below it.
        below_ring = ring_center_y + outer_radius
        controls_y = min(screen.height - 2, below_ring + 8)
        legend_y = min(controls_y - 1, below_ring + 6)
        action_y = min(legend_y - 1, below_ring + 4)
        session_info_y = min(action_y - 1, below_ring + 3)

        self._print_centered(
            screen,
            f"{snapshot.session_mode.value.title()} x{snapshot.session_mode.multiplier:g}"
            f"  |  Points: {self._app.points_total:g}",
            session_info_y,
        )
        action = "PAUSE" if snapshot.running else "RESUME" if snapshot.paused else "START"
        self._print_centered(
            screen,
            f"[ {action} ]",
            action_y,
            Screen.COLOUR_CYAN,
            Screen.A_BOLD,
        )
        self._print_centered(
            screen,
            "Bright ring = elapsed  Dim ring = remaining",
            legend_y,
        )
        self._print_centered(
            screen,
            "Space: start/pause/resume   Tab: mode   N: skip   R: reset counter   X: stop",
            controls_y,
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

    @classmethod
    def _draw_progress_ring(cls, screen: Screen, center_y: int, progress: float) -> None:
        center = (screen.width // 2, center_y)
        inner_radius, mid_radius, outer_radius = _ring_radii(screen.height)
        mid_points = _circle_points(mid_radius)
        # The progress ring is drawn first so the fixed-colour borders always
        # remain on top and are never affected by the elapsed/remaining fill.
        filled_points = math.ceil(progress * len(mid_points))
        for index, offset in enumerate(mid_points):
            colour, attr, character = (
                (Screen.COLOUR_CYAN, Screen.A_BOLD, PROGRESS_RING_ELAPSED_GLYPH)
                if index < filled_points
                else (Screen.COLOUR_WHITE, Screen.A_NORMAL, "*")
            )
            cls._print_ring_point(screen, center, offset, colour, attr, character)
        border_points = (*_circle_points(outer_radius), *_circle_points(inner_radius))
        for offset in border_points:
            cls._print_ring_point(screen, center, offset, Screen.COLOUR_WHITE, Screen.A_BOLD, "*")

    @staticmethod
    def _print_ring_point(
        screen: Screen,
        center: tuple[int, int],
        offset: tuple[int, int],
        colour: int,
        attr: int,
        character: str,
    ) -> None:
        x = center[0] + offset[0]
        y = center[1] + offset[1]
        if 0 <= x and x + len(character) <= screen.width and 2 <= y < screen.height:
            screen.print_at(character, x, y, colour, attr)

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
            f"Today goal progress: {goal.completed_focus_sessions}/ \
            {goal.goal_sessions} ({ratio}%)",
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

    def _draw_achievements(self, screen: Screen) -> None:
        snapshot = self._app.gamification_snapshot()
        screen.print_at("Mode: Achievements", 0, 3, Screen.COLOUR_WHITE, Screen.A_BOLD)
        line = 5

        if not snapshot.achievements_enabled:
            screen.print_at(
                "Achievements are disabled. Enable them in Configuration to track progress.",
                0,
                line,
                Screen.COLOUR_YELLOW,
            )
            screen.print_at(
                f"Status: {self._app.status_message}",
                0,
                min(screen.height - 1, line + 2),
                Screen.COLOUR_YELLOW,
            )
            return

        boost = snapshot.today_boost
        screen.print_at(
            f"Today's focus streak: {boost.consecutive_focus_completed} \
                | Active boost: x{boost.multiplier:g}",
            0,
            line,
            Screen.COLOUR_GREEN,
        )
        line += 1
        if boost.next_target is None:
            screen.print_at(
                "Next boost: max tier reached for today.", 0, line, Screen.COLOUR_GREEN
            )
        else:
            screen.print_at(
                f"Next boost at {boost.next_target} in a row: x{boost.next_multiplier:g}",
                0,
                line,
            )
        line += 2

        screen.print_at(
            "Completed Pomodoro achievements:", 0, line, Screen.COLOUR_CYAN, Screen.A_BOLD
        )
        line += 1
        for achievement in snapshot.completed_pomodoro_achievements:
            if line >= screen.height - 2:
                break
            marker = "Unlocked" if achievement.unlocked else "Locked  "
            screen.print_at(
                f"{marker} | {achievement.name:<24} | {achievement.current}/{achievement.target}",
                0,
                line,
            )
            line += 1

        line += 1
        if line < screen.height - 2:
            screen.print_at("Streak achievements:", 0, line, Screen.COLOUR_CYAN, Screen.A_BOLD)
            line += 1
        for achievement in snapshot.streak_achievements:
            if line >= screen.height - 2:
                break
            marker = "Unlocked" if achievement.unlocked else "Locked  "
            screen.print_at(
                f"{marker} | {achievement.name:<24} | {achievement.current}/{achievement.target}",
                0,
                line,
            )
            line += 1

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
            self._app.shutdown()
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
        if key in (ord("a"), ord("A")):
            self._mode = "achievements"
            return

        if self._mode == "timer":
            self._handle_timer_key(key)
        elif self._mode == "config":
            self._handle_config_key(key)

    def _handle_timer_key(self, key: int) -> None:
        if key == ord(" "):
            self._app.toggle_timer()
        elif key in (Screen.KEY_TAB, ord("\t")):
            self._app.cycle_session_mode()
        elif key in (ord("n"), ord("N")):
            self._app.skip_phase()
        elif key in (ord("r"), ord("R")):
            self._app.reset_focus_counter()
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
