from __future__ import annotations
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from .models import PhaseType, SessionStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class TimerSettings:
    focus_duration_min: int = 25
    short_break_duration_min: int = 5
    long_break_duration_min: int = 15
    long_break_interval: int = 4
    auto_start_next_phase: bool = True


@dataclass(slots=True)
class TimerSnapshot:
    phase: PhaseType
    running: bool
    paused: bool
    seconds_remaining: int
    phase_duration_seconds: int
    focus_sessions_completed_in_cycle: int


@dataclass(slots=True)
class TimerPhaseRecord:
    phase_type: PhaseType
    status: SessionStatus
    started_at: datetime
    ended_at: datetime
    planned_duration_seconds: int
    actual_duration_seconds: int
    interruption_reason: str | None = None


class PomodoroTimer:
    def __init__(self, settings: TimerSettings):
        self._settings = settings
        self._phase = PhaseType.FOCUS
        self._running = False
        self._paused = False
        self._focus_sessions_completed_in_cycle = 0
        self._seconds_remaining = self._phase_duration_seconds(self._phase)
        self._phase_started_at: datetime | None = None
        self._last_tick_monotonic: float | None = None

    def apply_settings(self, settings: TimerSettings) -> None:
        self._settings = settings
        if not self._running and not self._paused:
            self._seconds_remaining = self._phase_duration_seconds(self._phase)

    def snapshot(self) -> TimerSnapshot:
        return TimerSnapshot(
            phase=self._phase,
            running=self._running,
            paused=self._paused,
            seconds_remaining=self._seconds_remaining,
            phase_duration_seconds=self._phase_duration_seconds(self._phase),
            focus_sessions_completed_in_cycle=self._focus_sessions_completed_in_cycle,
        )

    def start(self, now: datetime | None = None) -> None:
        if self._running and not self._paused:
            return
        if self._phase_started_at is None:
            self._phase_started_at = now or utc_now()
        self._running = True
        self._paused = False
        self._last_tick_monotonic = time.monotonic()

    def pause(self) -> None:
        if not self._running:
            return
        self._running = False
        self._paused = True
        self._last_tick_monotonic = None

    def resume(self) -> None:
        if not self._paused:
            return
        self._running = True
        self._paused = False
        self._last_tick_monotonic = time.monotonic()

    def toggle(self) -> None:
        if self._running:
            self.pause()
        elif self._paused:
            self.resume()
        else:
            self.start()

    def stop(self, reason: str = "stopped") -> TimerPhaseRecord | None:
        record = self._build_interrupted_record(reason)
        self._running = False
        self._paused = False
        self._phase = PhaseType.FOCUS
        self._seconds_remaining = self._phase_duration_seconds(self._phase)
        self._phase_started_at = None
        self._last_tick_monotonic = None
        return record

    def skip(self, reason: str = "skipped") -> TimerPhaseRecord | None:
        if not self._running and not self._paused:
            return None
        interrupted = self._build_interrupted_record(reason)
        now = utc_now()
        self._transition_to_next_phase(now)
        if self._settings.auto_start_next_phase:
            self.start(now=now)
        else:
            self._running = False
            self._paused = False
        return interrupted

    def tick(self) -> list[TimerPhaseRecord]:
        if not self._running or self._last_tick_monotonic is None:
            return []
        elapsed_seconds = int(time.monotonic() - self._last_tick_monotonic)
        if elapsed_seconds <= 0:
            return []
        self._last_tick_monotonic += elapsed_seconds
        self._seconds_remaining = max(0, self._seconds_remaining - elapsed_seconds)
        if self._seconds_remaining > 0:
            return []

        now = utc_now()
        completed = self._build_completed_record(now)
        self._transition_to_next_phase(now)
        if self._settings.auto_start_next_phase:
            self.start(now=now)
        else:
            self._running = False
            self._paused = False
        return [completed]

    def _build_completed_record(self, ended_at: datetime) -> TimerPhaseRecord:
        started_at = self._phase_started_at or ended_at
        planned = self._phase_duration_seconds(self._phase)
        return TimerPhaseRecord(
            phase_type=self._phase,
            status=SessionStatus.COMPLETED,
            started_at=started_at,
            ended_at=ended_at,
            planned_duration_seconds=planned,
            actual_duration_seconds=planned,
        )

    def _build_interrupted_record(self, reason: str) -> TimerPhaseRecord | None:
        if self._phase_started_at is None:
            return None
        planned = self._phase_duration_seconds(self._phase)
        actual = max(0, planned - self._seconds_remaining)
        if actual == 0:
            return None
        return TimerPhaseRecord(
            phase_type=self._phase,
            status=SessionStatus.INTERRUPTED,
            started_at=self._phase_started_at,
            ended_at=utc_now(),
            planned_duration_seconds=planned,
            actual_duration_seconds=actual,
            interruption_reason=reason,
        )

    def _transition_to_next_phase(self, now: datetime) -> None:
        if self._phase == PhaseType.FOCUS:
            self._focus_sessions_completed_in_cycle += 1
            if self._focus_sessions_completed_in_cycle % self._settings.long_break_interval == 0:
                self._phase = PhaseType.LONG_BREAK
            else:
                self._phase = PhaseType.SHORT_BREAK
        else:
            self._phase = PhaseType.FOCUS
        self._seconds_remaining = self._phase_duration_seconds(self._phase)
        self._phase_started_at = now if self._settings.auto_start_next_phase else None
        self._last_tick_monotonic = (
            time.monotonic() if self._settings.auto_start_next_phase else None
        )

    def _phase_duration_seconds(self, phase: PhaseType) -> int:
        if phase == PhaseType.FOCUS:
            return self._settings.focus_duration_min * 60
        if phase == PhaseType.SHORT_BREAK:
            return self._settings.short_break_duration_min * 60
        return self._settings.long_break_duration_min * 60
