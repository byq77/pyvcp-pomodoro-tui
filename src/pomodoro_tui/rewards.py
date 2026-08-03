from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from sqlalchemy import func, select
from .models import RewardDefinition, RewardPurchase

if TYPE_CHECKING:
    from .db import SessionFactory


@dataclass(slots=True)
class RewardValues:
    """Detached representation of a reward definition."""

    id: int
    name: str
    cost_points: float
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class RewardPurchaseValues:
    """Detached representation of a purchase, including immutable snapshot fields."""

    id: int
    reward_id: int | None
    reward_name_snapshot: str
    unit_cost_points_snapshot: float
    quantity: int
    total_cost_points: float
    purchased_at: datetime


@dataclass(slots=True)
class RewardsSnapshot:
    """Aggregated rewards data for rendering the rewards screen."""

    rewards: list[RewardValues]
    recent_purchases: list[RewardPurchaseValues]
    total_spent_points: float
    total_rewards_acquired: int
    available_points: float


def _to_reward_values(row: RewardDefinition) -> RewardValues:
    return RewardValues(
        id=row.id,
        name=row.name,
        cost_points=row.cost_points,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_purchase_values(row: RewardPurchase) -> RewardPurchaseValues:
    return RewardPurchaseValues(
        id=row.id,
        reward_id=row.reward_id,
        reward_name_snapshot=row.reward_name_snapshot,
        unit_cost_points_snapshot=row.unit_cost_points_snapshot,
        quantity=row.quantity,
        total_cost_points=row.total_cost_points,
        purchased_at=row.purchased_at,
    )


class RewardNotFoundError(Exception):
    """Raised when a reward id does not correspond to an existing reward."""

    def __init__(self, reward_id: int):
        self.reward_id = reward_id
        super().__init__(f"Reward #{reward_id} was not found (it may have been deleted).")


class InsufficientPointsError(Exception):
    """Raised when a purchase would exceed the available points balance."""

    def __init__(self, required: float, available: float):
        self.required = required
        self.available = available
        self.missing = required - available
        super().__init__(
            f"Need {required:g} points, but only {available:g} are available "
            f"(missing {self.missing:g})."
        )


def _validate_reward(name: str, cost_points: float) -> None:
    if not name.strip():
        msg = "Reward name must not be empty."
        raise ValueError(msg)
    if cost_points <= 0:
        msg = f"Reward cost must be greater than 0, got {cost_points:g}."
        raise ValueError(msg)


class RewardsService:
    """Persists reward definitions and purchases, and computes spending aggregates."""

    def __init__(self, session_factory: SessionFactory):
        self._session_factory = session_factory

    def list_rewards(self) -> list[RewardValues]:
        with self._session_factory() as session:
            statement = select(RewardDefinition).order_by(
                RewardDefinition.created_at.asc(), RewardDefinition.id.asc()
            )
            return [_to_reward_values(row) for row in session.scalars(statement)]

    def create_reward(self, name: str, cost_points: float) -> RewardValues:
        _validate_reward(name, cost_points)
        with self._session_factory() as session:
            row = RewardDefinition(name=name.strip(), cost_points=cost_points)
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_reward_values(row)

    def update_reward(self, reward_id: int, name: str, cost_points: float) -> RewardValues:
        _validate_reward(name, cost_points)
        with self._session_factory() as session:
            row = session.get(RewardDefinition, reward_id)
            if row is None:
                raise RewardNotFoundError(reward_id)
            row.name = name.strip()
            row.cost_points = cost_points
            row.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            return _to_reward_values(row)

    def delete_reward(self, reward_id: int) -> None:
        with self._session_factory() as session:
            row = session.get(RewardDefinition, reward_id)
            if row is None:
                raise RewardNotFoundError(reward_id)
            # Detach past purchases from the deleted reward; their snapshot fields
            # already preserve the historical name/cost, so history stays intact.
            purchases = session.scalars(
                select(RewardPurchase).where(RewardPurchase.reward_id == reward_id)
            )
            for purchase in purchases:
                purchase.reward_id = None
            session.delete(row)
            session.commit()

    def purchase(
        self, reward_id: int, quantity: int, available_points: float
    ) -> RewardPurchaseValues:
        """Buy `quantity` units of a reward, validating affordability first.

        Raises `RewardNotFoundError` if the reward no longer exists, `ValueError`
        if quantity is not a positive integer, or `InsufficientPointsError` if
        `available_points` cannot cover the total cost.
        """
        if quantity < 1:
            msg = f"Quantity must be at least 1, got {quantity}."
            raise ValueError(msg)
        with self._session_factory() as session:
            reward = session.get(RewardDefinition, reward_id)
            if reward is None:
                raise RewardNotFoundError(reward_id)
            total_cost = reward.cost_points * quantity
            if total_cost > available_points:
                raise InsufficientPointsError(total_cost, available_points)
            purchase = RewardPurchase(
                reward_id=reward.id,
                reward_name_snapshot=reward.name,
                unit_cost_points_snapshot=reward.cost_points,
                quantity=quantity,
                total_cost_points=total_cost,
            )
            session.add(purchase)
            session.commit()
            session.refresh(purchase)
            return _to_purchase_values(purchase)

    def total_spent_points(self) -> float:
        with self._session_factory() as session:
            statement = select(func.coalesce(func.sum(RewardPurchase.total_cost_points), 0.0))
            return float(session.scalar(statement) or 0.0)

    def total_rewards_acquired(self) -> int:
        with self._session_factory() as session:
            statement = select(func.coalesce(func.sum(RewardPurchase.quantity), 0))
            return int(session.scalar(statement) or 0)

    def recent_purchases(self, limit: int = 20) -> list[RewardPurchaseValues]:
        with self._session_factory() as session:
            statement = (
                select(RewardPurchase).order_by(RewardPurchase.purchased_at.desc()).limit(limit)
            )
            return [_to_purchase_values(row) for row in session.scalars(statement)]

    def snapshot(self, available_points: float, *, recent_limit: int = 10) -> RewardsSnapshot:
        return RewardsSnapshot(
            rewards=self.list_rewards(),
            recent_purchases=self.recent_purchases(limit=recent_limit),
            total_spent_points=self.total_spent_points(),
            total_rewards_acquired=self.total_rewards_acquired(),
            available_points=available_points,
        )
