from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from sqlalchemy import func, select
from .models import PhaseType, PomodoroSession, SessionStatus

if TYPE_CHECKING:
    from .config import ConfigValues
    from .db import SessionFactory
    from .timer import TimerPhaseRecord

POINTS_PER_MINUTE = 1


@dataclass(slots=True)
class DailyTotal:
    day: date
    completed_sessions: int
    completed_focus_sessions: int
    total_seconds: int


@dataclass(slots=True)
class GoalProgress:
    day: date
    completed_focus_sessions: int
    goal_sessions: int

    @property
    def completion_ratio(self) -> float:
        return self.completed_focus_sessions / self.goal_sessions


@dataclass(slots=True)
class HistorySnapshot:
    recent_sessions: list[PomodoroSession]
    daily_totals: list[DailyTotal]
    current_streak_days: int
    goal_progress_today: GoalProgress


def points_for_duration(actual_duration_seconds: int) -> int:
    """Return the points earned for a completed focus phase of the given duration.

    One point is awarded per full minute, matching the documented reward of
    25 points for a 25-minute focus session.
    """
    return (actual_duration_seconds // 60) * POINTS_PER_MINUTE


class HistoryService:
    def __init__(self, session_factory: SessionFactory):
        self._session_factory = session_factory

    def record(self, record: TimerPhaseRecord) -> None:
        with self._session_factory() as session:
            session.add(
                PomodoroSession(
                    phase_type=record.phase_type,
                    status=record.status,
                    started_at=record.started_at,
                    ended_at=record.ended_at,
                    planned_duration_seconds=record.planned_duration_seconds,
                    actual_duration_seconds=record.actual_duration_seconds,
                    interruption_reason=record.interruption_reason,
                )
            )
            session.commit()

    def snapshot(self, config: ConfigValues) -> HistorySnapshot:
        recent_sessions = self.recent_sessions(limit=20)
        daily_totals = self.daily_totals(
            days=config.history_days_visible,
            include_breaks=config.include_breaks_in_totals,
        )
        goal_progress = self.goal_progress_for_day(date.today(), config.daily_goal_sessions)
        streak = self.current_streak(config)
        return HistorySnapshot(
            recent_sessions=recent_sessions,
            daily_totals=daily_totals,
            current_streak_days=streak,
            goal_progress_today=goal_progress,
        )

    def total_points(self) -> int:
        with self._session_factory() as session:
            statement = select(
                func.coalesce(func.sum(PomodoroSession.actual_duration_seconds), 0)
            ).where(
                PomodoroSession.phase_type == PhaseType.FOCUS,
                PomodoroSession.status == SessionStatus.COMPLETED,
            )
            total_seconds = session.scalar(statement) or 0
        return points_for_duration(total_seconds)

    def recent_sessions(self, limit: int = 20) -> list[PomodoroSession]:
        with self._session_factory() as session:
            statement = (
                select(PomodoroSession).order_by(PomodoroSession.started_at.desc()).limit(limit)
            )
            return list(session.scalars(statement))

    def daily_totals(self, *, days: int, include_breaks: bool) -> list[DailyTotal]:
        start_day = date.today() - timedelta(days=days - 1)
        start_dt = datetime.combine(start_day, datetime.min.time(), tzinfo=UTC)

        with self._session_factory() as session:
            statement = select(PomodoroSession).where(PomodoroSession.started_at >= start_dt)
            rows = list(session.scalars(statement))

        grouped: dict[date, dict[str, int]] = defaultdict(
            lambda: {"completed": 0, "focus_completed": 0, "total_seconds": 0}
        )
        for row in rows:
            day_key = row.started_at.date()
            if row.status != SessionStatus.COMPLETED:
                continue
            if row.phase_type == PhaseType.FOCUS:
                grouped[day_key]["focus_completed"] += 1
            if include_breaks or row.phase_type == PhaseType.FOCUS:
                grouped[day_key]["completed"] += 1
                grouped[day_key]["total_seconds"] += row.actual_duration_seconds

        totals: list[DailyTotal] = []
        for offset in range(days):
            current = start_day + timedelta(days=offset)
            values = grouped[current]
            totals.append(
                DailyTotal(
                    day=current,
                    completed_sessions=values["completed"],
                    completed_focus_sessions=values["focus_completed"],
                    total_seconds=values["total_seconds"],
                )
            )
        totals.reverse()
        return totals

    def goal_progress_for_day(self, day: date, goal_sessions: int) -> GoalProgress:
        start_dt = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        end_dt = start_dt + timedelta(days=1)

        with self._session_factory() as session:
            statement = (
                select(PomodoroSession)
                .where(PomodoroSession.started_at >= start_dt)
                .where(PomodoroSession.started_at < end_dt)
            )
            rows = list(session.scalars(statement))

        completed_focus = sum(
            1
            for row in rows
            if row.phase_type == PhaseType.FOCUS and row.status == SessionStatus.COMPLETED
        )
        return GoalProgress(
            day=day,
            completed_focus_sessions=completed_focus,
            goal_sessions=goal_sessions,
        )

    def current_streak(self, config: ConfigValues) -> int:
        goal = config.daily_goal_sessions
        streak = 0
        cursor = date.today()

        while True:
            if not config.track_weekends and cursor.weekday() >= 5:
                cursor -= timedelta(days=1)
                continue
            progress = self.goal_progress_for_day(cursor, goal)
            completed_focus = progress.completed_focus_sessions
            if config.streak_requires_goal:
                meets_target = completed_focus >= goal
            else:
                meets_target = completed_focus > 0
            if not meets_target:
                break
            streak += 1
            cursor -= timedelta(days=1)
        return streak
