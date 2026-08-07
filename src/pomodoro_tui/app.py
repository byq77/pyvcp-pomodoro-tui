from __future__ import annotations
from dataclasses import replace
from importlib.resources import files
from typing import TYPE_CHECKING
from playsound3 import playsound

if TYPE_CHECKING:
    from pathlib import Path
    from .config import ConfigValues

from .config import ConfigService
from .db import create_engine_and_session_factory, init_db
from .debt import (
    DebtNotFoundError,
    DebtPaymentValues,
    DebtService,
    DebtSnapshot,
    DebtValues,
    InsufficientPointsError as DebtInsufficientPointsError,
    NoDebtToPayError,
)
from .history import GamificationSnapshot, HistoryService, HistorySnapshot, RewardHistoryStats
from .models import PhaseType, SessionStatus
from .rewards import (
    InsufficientPointsError,
    RewardNotFoundError,
    RewardPurchaseValues,
    RewardsService,
    RewardsSnapshot,
    RewardValues,
)
from .runtime_state import RuntimeStateService
from .timer import PomodoroTimer

SESSION_END_SOUND_PATH = files("pomodoro_tui").joinpath("assets", "Clock-sound-effect.mp3")


class PomodoroApplication:
    def __init__(self, db_path: Path | None = None):
        engine, session_factory = create_engine_and_session_factory(db_path=db_path)
        init_db(engine)

        self._config_service = ConfigService(session_factory)
        self._history_service = HistoryService(session_factory)
        self._runtime_state_service = RuntimeStateService(session_factory)
        self._rewards_service = RewardsService(session_factory)
        self._debt_service = DebtService(session_factory)
        self.config = self._config_service.get_or_create()
        self.timer = PomodoroTimer(self.config.to_timer_settings())
        self.status_message = "Ready."
        self.points_total = self._available_points_total()
        self._restore_timer_state()

    def tick(self) -> None:
        records = self.timer.tick()
        for record in records:
            earned = self._history_service.points_for_record(record)
            self._history_service.record(record)
            playsound(str(SESSION_END_SOUND_PATH), block=False)
            self.status_message = f"Completed {record.phase_type.value.replace('_', ' ')}."
            if record.phase_type == PhaseType.FOCUS and record.status == SessionStatus.COMPLETED:
                self.points_total += earned
                self.status_message += f" +{earned:g} points!"
        if records:
            self._sync_runtime_state()

    def toggle_timer(self) -> None:
        before = self.timer.snapshot()
        self.timer.toggle()
        after = self.timer.snapshot()
        if not before.running and not before.paused and after.running:
            self.status_message = "Timer started."
        elif before.running and after.paused:
            self.status_message = "Timer paused."
        elif before.paused and after.running:
            self.status_message = "Timer resumed."
        self._sync_runtime_state()

    def reset_focus_counter(self) -> None:
        self.timer.reset_focus_counter()
        self.status_message = "Focus counter reset."
        self._sync_runtime_state()

    def adjust_focus_counter(self, delta: int) -> None:
        before = self.timer.snapshot().focus_sessions_completed_in_cycle
        after = self.timer.adjust_focus_counter(delta)
        if after == before:
            self.status_message = "Focus counter already at zero."
        else:
            self.status_message = f"Focus counter: {after}."
        self._sync_runtime_state()

    def cycle_session_mode(self) -> None:
        mode = self.timer.cycle_session_mode()
        self.status_message = f"Session mode: {mode.value.title()} (x{mode.multiplier:g})."
        self._sync_runtime_state()

    def skip_phase(self) -> None:
        record = self.timer.skip()
        if record is None:
            self.status_message = "Start the timer before skipping a phase."
            return
        self._history_service.record(record)
        self.status_message = "Phase skipped."
        self._sync_runtime_state()

    def stop_timer(self, reason: str = "stopped") -> None:
        record = self.timer.stop(reason=reason)
        if record is not None:
            self._history_service.record(record)
        self.status_message = "Timer stopped."
        self._sync_runtime_state()

    def shutdown(self) -> None:
        self._sync_runtime_state()

    def build_config_draft(self) -> ConfigValues:
        return replace(self.config)

    def save_config(self, values: ConfigValues) -> None:
        self.config = self._config_service.save(values)
        self.timer.apply_settings(self.config.to_timer_settings())
        self.status_message = "Configuration saved."
        self._sync_runtime_state()

    def history_snapshot(self) -> HistorySnapshot:
        reward_stats = RewardHistoryStats(
            total_spent_points=self._rewards_service.total_spent_points(),
            total_rewards_acquired=self._rewards_service.total_rewards_acquired(),
        )
        return self._history_service.snapshot(self.config, reward_stats)

    def gamification_snapshot(self) -> GamificationSnapshot:
        return self._history_service.gamification_snapshot(self.config)

    def rewards_snapshot(self) -> RewardsSnapshot:
        return self._rewards_service.snapshot(self.points_total)

    def create_reward(self, name: str, cost_points: float) -> RewardValues | None:
        try:
            reward = self._rewards_service.create_reward(name, cost_points)
        except ValueError as exc:
            self.status_message = f"Reward error: {exc}"
            return None
        self.status_message = f"Added reward '{reward.name}' ({reward.cost_points:g} pts)."
        return reward

    def update_reward(self, reward_id: int, name: str, cost_points: float) -> RewardValues | None:
        try:
            reward = self._rewards_service.update_reward(reward_id, name, cost_points)
        except (ValueError, RewardNotFoundError) as exc:
            self.status_message = f"Reward error: {exc}"
            return None
        self.status_message = f"Updated reward '{reward.name}'."
        return reward

    def delete_reward(self, reward_id: int) -> bool:
        try:
            self._rewards_service.delete_reward(reward_id)
        except RewardNotFoundError as exc:
            self.status_message = f"Reward error: {exc}"
            return False
        self.status_message = "Reward deleted."
        return True

    def purchase_reward(self, reward_id: int, quantity: int) -> RewardPurchaseValues | None:
        try:
            purchase = self._rewards_service.purchase(reward_id, quantity, self.points_total)
        except (ValueError, RewardNotFoundError) as exc:
            self.status_message = f"Purchase error: {exc}"
            return None
        except InsufficientPointsError as exc:
            self.status_message = f"Not enough points: missing {exc.missing:g}."
            return None
        self.points_total -= purchase.total_cost_points
        self.status_message = (
            f"Bought {purchase.quantity}x '{purchase.reward_name_snapshot}' "
            f"for {purchase.total_cost_points:g} points."
        )
        return purchase

    def debt_snapshot(self) -> DebtSnapshot:
        return self._debt_service.snapshot(self.points_total)

    def create_debt_entry(self, description: str, amount: float) -> DebtValues | None:
        try:
            entry = self._debt_service.create_entry(description, amount)
        except ValueError as exc:
            self.status_message = f"Debt error: {exc}"
            return None
        self.status_message = f"Added debt '{entry.description}' ({entry.amount:g})."
        return entry

    def update_debt_entry(
        self, debt_id: int, description: str, amount: float
    ) -> DebtValues | None:
        try:
            entry = self._debt_service.update_entry(debt_id, description, amount)
        except (ValueError, DebtNotFoundError) as exc:
            self.status_message = f"Debt error: {exc}"
            return None
        self.status_message = f"Updated debt '{entry.description}'."
        return entry

    def delete_debt_entry(self, debt_id: int) -> bool:
        try:
            self._debt_service.delete_entry(debt_id)
        except DebtNotFoundError as exc:
            self.status_message = f"Debt error: {exc}"
            return False
        self.status_message = "Debt entry deleted."
        return True

    def pay_off_debt(self, amount_points: float) -> DebtPaymentValues | None:
        try:
            payment = self._debt_service.pay_off(amount_points, self.points_total)
        except ValueError as exc:
            self.status_message = f"Payoff error: {exc}"
            return None
        except NoDebtToPayError as exc:
            self.status_message = f"Payoff error: {exc}"
            return None
        except DebtInsufficientPointsError as exc:
            self.status_message = f"Not enough points: missing {exc.missing:g}."
            return None
        self.points_total -= payment.amount_points
        self.status_message = f"Paid off {payment.amount_points:g} points of debt."
        return payment

    def _sync_runtime_state(self) -> None:
        runtime_state = self.timer.export_runtime_state()
        if runtime_state is None:
            self._runtime_state_service.clear()
            return
        self._runtime_state_service.save(runtime_state)

    def _available_points_total(self) -> float:
        return (
            self._history_service.total_points()
            - self._rewards_service.total_spent_points()
            - self._debt_service.total_paid_points()
        )

    def _restore_timer_state(self) -> None:
        runtime_state = self._runtime_state_service.load_for_today()
        if runtime_state is None:
            return
        self.timer.restore_runtime_state(runtime_state)
        self.status_message = "Restored timer from earlier today."
