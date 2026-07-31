from __future__ import annotations
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from .models import AppTimerState
from .timer import TimerRuntimeState

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from .db import SessionFactory


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class RuntimeStateService:
    def __init__(self, session_factory: SessionFactory):
        self._session_factory = session_factory

    def load_for_today(self) -> TimerRuntimeState | None:
        with self._session_factory() as session:
            row = session.get(AppTimerState, 1)
            if row is None:
                return None
            saved_at = _ensure_utc(row.saved_at)
            saved_day_local = saved_at.astimezone().date()
            today_local = datetime.now(UTC).astimezone().date()
            if saved_day_local != today_local:
                session.delete(row)
                session.commit()
                return None
            return TimerRuntimeState(
                phase=row.phase_type,
                running=row.running,
                paused=row.paused,
                seconds_remaining=row.seconds_remaining,
                focus_sessions_completed_in_cycle=row.focus_sessions_completed_in_cycle,
                phase_started_at=_ensure_utc(row.phase_started_at)
                if row.phase_started_at
                else None,
                saved_at=saved_at,
            )

    def save(self, state: TimerRuntimeState) -> None:
        with self._session_factory() as session:
            row = session.get(AppTimerState, 1)
            if row is None:
                row = AppTimerState(id=1)
                session.add(row)
            row.phase_type = state.phase
            row.running = state.running
            row.paused = state.paused
            row.seconds_remaining = state.seconds_remaining
            row.focus_sessions_completed_in_cycle = state.focus_sessions_completed_in_cycle
            row.phase_started_at = state.phase_started_at
            row.saved_at = _ensure_utc(state.saved_at)
            session.commit()

    def clear(self) -> None:
        with self._session_factory() as session:
            row = session.get(AppTimerState, 1)
            if row is None:
                return
            session.delete(row)
            session.commit()
