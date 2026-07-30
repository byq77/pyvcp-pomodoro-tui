from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC, datetime
from sqlalchemy.orm import Session
from .db import SessionFactory
from .models import AppConfig
from .timer import TimerSettings


@dataclass(slots=True)
class ConfigValues:
    focus_duration_min: int = 25
    short_break_duration_min: int = 5
    long_break_duration_min: int = 15
    long_break_interval: int = 4
    auto_start_next_phase: bool = True
    daily_goal_sessions: int = 8
    include_breaks_in_totals: bool = False
    streak_requires_goal: bool = False
    track_weekends: bool = True
    history_days_visible: int = 14

    def to_timer_settings(self) -> TimerSettings:
        return TimerSettings(
            focus_duration_min=self.focus_duration_min,
            short_break_duration_min=self.short_break_duration_min,
            long_break_duration_min=self.long_break_duration_min,
            long_break_interval=self.long_break_interval,
            auto_start_next_phase=self.auto_start_next_phase,
        )


def _validate(values: ConfigValues) -> None:
    if values.focus_duration_min < 1:
        raise ValueError("focus_duration_min must be at least 1")
    if values.short_break_duration_min < 1:
        raise ValueError("short_break_duration_min must be at least 1")
    if values.long_break_duration_min < 1:
        raise ValueError("long_break_duration_min must be at least 1")
    if values.long_break_interval < 1:
        raise ValueError("long_break_interval must be at least 1")
    if values.daily_goal_sessions < 1:
        raise ValueError("daily_goal_sessions must be at least 1")
    if values.history_days_visible < 1:
        raise ValueError("history_days_visible must be at least 1")


def _to_values(row: AppConfig) -> ConfigValues:
    return ConfigValues(
        focus_duration_min=row.focus_duration_min,
        short_break_duration_min=row.short_break_duration_min,
        long_break_duration_min=row.long_break_duration_min,
        long_break_interval=row.long_break_interval,
        auto_start_next_phase=row.auto_start_next_phase,
        daily_goal_sessions=row.daily_goal_sessions,
        include_breaks_in_totals=row.include_breaks_in_totals,
        streak_requires_goal=row.streak_requires_goal,
        track_weekends=row.track_weekends,
        history_days_visible=row.history_days_visible,
    )


class ConfigService:
    def __init__(self, session_factory: SessionFactory):
        self._session_factory = session_factory

    def get_or_create(self) -> ConfigValues:
        with self._session_factory() as session:
            row = self._get_or_create_row(session)
            session.commit()
            return _to_values(row)

    def save(self, values: ConfigValues) -> ConfigValues:
        _validate(values)
        with self._session_factory() as session:
            row = self._get_or_create_row(session)
            row.focus_duration_min = values.focus_duration_min
            row.short_break_duration_min = values.short_break_duration_min
            row.long_break_duration_min = values.long_break_duration_min
            row.long_break_interval = values.long_break_interval
            row.auto_start_next_phase = values.auto_start_next_phase
            row.daily_goal_sessions = values.daily_goal_sessions
            row.include_breaks_in_totals = values.include_breaks_in_totals
            row.streak_requires_goal = values.streak_requires_goal
            row.track_weekends = values.track_weekends
            row.history_days_visible = values.history_days_visible
            row.updated_at = datetime.now(UTC)
            session.commit()
            return _to_values(row)

    @staticmethod
    def _get_or_create_row(session: Session) -> AppConfig:
        row = session.get(AppConfig, 1)
        if row is None:
            row = AppConfig(id=1)
            session.add(row)
            session.flush()
        return row
