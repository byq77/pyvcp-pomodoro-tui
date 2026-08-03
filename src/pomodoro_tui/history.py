from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from sqlalchemy import func, select
from .models import PhaseType, PomodoroSession, SessionMode, SessionStatus

if TYPE_CHECKING:
    from .config import ConfigValues
    from .db import SessionFactory
    from .timer import TimerPhaseRecord

POINTS_PER_MINUTE = 1
BOOST_THRESHOLDS: tuple[tuple[int, float], ...] = (
    (4, 1.5),
    (8, 2.0),
    (12, 3.0),
    (16, 4.0),
)
POMODORO_ACHIEVEMENT_TARGETS: tuple[int, ...] = (10, 100, 200, 500, 1000)
STREAK_ACHIEVEMENT_TARGETS: tuple[int, ...] = (3, 7, 14, 30, 100)


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
class RewardHistoryStats:
    """Aggregated reward-spending statistics surfaced in the History view."""

    total_spent_points: float
    total_rewards_acquired: int


@dataclass(slots=True)
class HistorySnapshot:
    recent_sessions: list[PomodoroSession]
    daily_totals: list[DailyTotal]
    current_streak_days: int
    goal_progress_today: GoalProgress
    reward_stats: RewardHistoryStats


@dataclass(slots=True)
class AchievementProgress:
    name: str
    current: int
    target: int
    unlocked: bool


@dataclass(slots=True)
class BoostProgress:
    consecutive_focus_completed: int
    multiplier: float
    next_target: int | None
    next_multiplier: float | None


@dataclass(slots=True)
class GamificationSnapshot:
    achievements_enabled: bool
    completed_pomodoro_achievements: list[AchievementProgress]
    streak_achievements: list[AchievementProgress]
    today_boost: BoostProgress


def points_for_duration(actual_duration_seconds: int, session_mode: SessionMode) -> float:
    """Return the base points earned for a completed focus phase duration."""
    return (actual_duration_seconds // 60) * POINTS_PER_MINUTE * session_mode.multiplier


def boost_multiplier_for_streak(consecutive_focus_completed: int) -> float:
    """Return the streak boost multiplier for a same-day completed-focus streak."""
    multiplier = 1.0
    for threshold, value in BOOST_THRESHOLDS:
        if consecutive_focus_completed >= threshold:
            multiplier = value
    return multiplier


def points_for_completed_focus(
    actual_duration_seconds: int,
    session_mode: SessionMode,
    consecutive_focus_completed: int,
) -> float:
    """Return boosted points for a completed focus phase."""
    return points_for_duration(
        actual_duration_seconds, session_mode
    ) * boost_multiplier_for_streak(consecutive_focus_completed)


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
                    session_mode=record.session_mode,
                    interruption_reason=record.interruption_reason,
                )
            )
            session.commit()

    def points_for_record(self, record: TimerPhaseRecord) -> float:
        """Return points to award if the given record is persisted."""
        if record.phase_type != PhaseType.FOCUS or record.status != SessionStatus.COMPLETED:
            return 0.0

        day = record.started_at.date()
        existing_rows = self._focus_rows_for_day(day)
        prior_streak = self._consecutive_completed_focus(existing_rows)
        current_streak = prior_streak + 1
        return points_for_completed_focus(
            record.actual_duration_seconds,
            record.session_mode,
            current_streak,
        )

    def snapshot(self, config: ConfigValues, reward_stats: RewardHistoryStats) -> HistorySnapshot:
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
            reward_stats=reward_stats,
        )

    def gamification_snapshot(self, config: ConfigValues) -> GamificationSnapshot:
        completed_focus_total = self.completed_focus_sessions_total()
        current_streak = self.current_streak(config)
        today_boost = self.today_boost()
        return GamificationSnapshot(
            achievements_enabled=config.achievements_enabled,
            completed_pomodoro_achievements=[
                AchievementProgress(
                    name=f"{target} completed pomodoros",
                    current=completed_focus_total,
                    target=target,
                    unlocked=completed_focus_total >= target,
                )
                for target in POMODORO_ACHIEVEMENT_TARGETS
            ],
            streak_achievements=[
                AchievementProgress(
                    name=f"{target}-day streak",
                    current=current_streak,
                    target=target,
                    unlocked=current_streak >= target,
                )
                for target in STREAK_ACHIEVEMENT_TARGETS
            ],
            today_boost=today_boost,
        )

    def completed_focus_sessions_total(self) -> int:
        with self._session_factory() as session:
            statement = select(func.count(PomodoroSession.id)).where(
                PomodoroSession.phase_type == PhaseType.FOCUS,
                PomodoroSession.status == SessionStatus.COMPLETED,
            )
            return int(session.scalar(statement) or 0)

    def total_points(self) -> float:
        with self._session_factory() as session:
            statement = (
                select(PomodoroSession)
                .where(PomodoroSession.phase_type == PhaseType.FOCUS)
                .order_by(PomodoroSession.started_at.asc(), PomodoroSession.id.asc())
            )
            rows = list(session.scalars(statement))

        total = 0.0
        streak = 0
        current_day: date | None = None
        for row in rows:
            row_day = row.started_at.date()
            if current_day != row_day:
                current_day = row_day
                streak = 0
            if row.status == SessionStatus.COMPLETED:
                streak += 1
                total += points_for_completed_focus(
                    row.actual_duration_seconds,
                    row.session_mode,
                    streak,
                )
            elif row.status == SessionStatus.INTERRUPTED:
                streak = 0
        return total

    def today_boost(self) -> BoostProgress:
        today = date.today()
        rows = self._focus_rows_for_day(today)
        streak = self._consecutive_completed_focus(rows)
        multiplier = boost_multiplier_for_streak(streak)
        next_target = None
        next_multiplier = None
        for threshold, candidate_multiplier in BOOST_THRESHOLDS:
            if threshold > streak:
                next_target = threshold
                next_multiplier = candidate_multiplier
                break
        return BoostProgress(
            consecutive_focus_completed=streak,
            multiplier=multiplier,
            next_target=next_target,
            next_multiplier=next_multiplier,
        )

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

    def _focus_rows_for_day(self, day: date) -> list[PomodoroSession]:
        start_dt = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        end_dt = start_dt + timedelta(days=1)
        with self._session_factory() as session:
            statement = (
                select(PomodoroSession)
                .where(PomodoroSession.phase_type == PhaseType.FOCUS)
                .where(PomodoroSession.started_at >= start_dt)
                .where(PomodoroSession.started_at < end_dt)
                .order_by(PomodoroSession.started_at.asc(), PomodoroSession.id.asc())
            )
            return list(session.scalars(statement))

    @staticmethod
    def _consecutive_completed_focus(rows: list[PomodoroSession]) -> int:
        streak = 0
        for row in rows:
            if row.status == SessionStatus.COMPLETED:
                streak += 1
            elif row.status == SessionStatus.INTERRUPTED:
                streak = 0
        return streak
