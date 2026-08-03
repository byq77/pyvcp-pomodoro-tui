from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PhaseType(str, Enum):
    FOCUS = "focus"
    SHORT_BREAK = "short_break"
    LONG_BREAK = "long_break"


class SessionStatus(str, Enum):
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"


class SessionMode(str, Enum):
    SILENT = "silent"
    NORMAL = "normal"
    DIRTY = "dirty"

    @property
    def multiplier(self) -> float:
        return {
            SessionMode.SILENT: 1.5,
            SessionMode.NORMAL: 1.0,
            SessionMode.DIRTY: 0.5,
        }[self]


class AppConfig(Base):
    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    focus_duration_min: Mapped[int] = mapped_column(Integer, default=25)
    short_break_duration_min: Mapped[int] = mapped_column(Integer, default=5)
    long_break_duration_min: Mapped[int] = mapped_column(Integer, default=15)
    long_break_interval: Mapped[int] = mapped_column(Integer, default=4)
    auto_start_next_phase: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_goal_sessions: Mapped[int] = mapped_column(Integer, default=8)
    include_breaks_in_totals: Mapped[bool] = mapped_column(Boolean, default=False)
    streak_requires_goal: Mapped[bool] = mapped_column(Boolean, default=False)
    track_weekends: Mapped[bool] = mapped_column(Boolean, default=True)
    history_days_visible: Mapped[int] = mapped_column(Integer, default=14)
    achievements_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class PomodoroSession(Base):
    __tablename__ = "pomodoro_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phase_type: Mapped[PhaseType] = mapped_column(SqlEnum(PhaseType), nullable=False)
    status: Mapped[SessionStatus] = mapped_column(
        SqlEnum(SessionStatus), nullable=False, default=SessionStatus.COMPLETED
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planned_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    session_mode: Mapped[SessionMode] = mapped_column(
        SqlEnum(SessionMode, values_callable=lambda modes: [mode.value for mode in modes]),
        nullable=False,
        default=SessionMode.NORMAL,
    )
    interruption_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)


class RewardDefinition(Base):
    __tablename__ = "reward_definition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    cost_points: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class RewardPurchase(Base):
    __tablename__ = "reward_purchase"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reward_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("reward_definition.id", ondelete="SET NULL"), nullable=True
    )
    reward_name_snapshot: Mapped[str] = mapped_column(String(120), nullable=False)
    unit_cost_points_snapshot: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_cost_points: Mapped[float] = mapped_column(Float, nullable=False)
    purchased_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class AppTimerState(Base):
    __tablename__ = "app_timer_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    phase_type: Mapped[PhaseType] = mapped_column(SqlEnum(PhaseType), nullable=False)
    running: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seconds_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    focus_sessions_completed_in_cycle: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    session_mode: Mapped[SessionMode] = mapped_column(
        SqlEnum(SessionMode, values_callable=lambda modes: [mode.value for mode in modes]),
        nullable=False,
        default=SessionMode.NORMAL,
    )
    phase_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
