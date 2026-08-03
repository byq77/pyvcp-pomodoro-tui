from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from sqlalchemy import func, select
from .models import DebtEntry, DebtPayment

if TYPE_CHECKING:
    from .db import SessionFactory


@dataclass(slots=True)
class DebtValues:
    """Detached representation of a one-off debt entry."""

    id: int
    description: str
    amount: float
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class DebtPaymentValues:
    """Detached representation of a payment made against the total debt."""

    id: int
    amount_points: float
    paid_at: datetime


@dataclass(slots=True)
class DebtSnapshot:
    """Aggregated debt data for rendering the debt screen."""

    entries: list[DebtValues]
    recent_payments: list[DebtPaymentValues]
    total_debt: float
    total_paid_points: float
    available_points: float


def _to_debt_values(row: DebtEntry) -> DebtValues:
    return DebtValues(
        id=row.id,
        description=row.description,
        amount=row.amount,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_payment_values(row: DebtPayment) -> DebtPaymentValues:
    return DebtPaymentValues(
        id=row.id,
        amount_points=row.amount_points,
        paid_at=row.paid_at,
    )


class DebtNotFoundError(Exception):
    """Raised when a debt entry id does not correspond to an existing entry."""

    def __init__(self, debt_id: int):
        self.debt_id = debt_id
        super().__init__(f"Debt entry #{debt_id} was not found (it may have been deleted).")


class NoDebtToPayError(Exception):
    """Raised when a payoff is attempted while there is no outstanding debt."""

    def __init__(self):
        super().__init__("There is no outstanding debt to pay off.")


class InsufficientPointsError(Exception):
    """Raised when a debt payoff would exceed the available points balance."""

    def __init__(self, required: float, available: float):
        self.required = required
        self.available = available
        self.missing = required - available
        super().__init__(
            f"Need {required:g} points, but only {available:g} are available "
            f"(missing {self.missing:g})."
        )


def _validate_debt(description: str, amount: float) -> None:
    if not description.strip():
        msg = "Debt description must not be empty."
        raise ValueError(msg)
    if amount <= 0:
        msg = f"Debt amount must be greater than 0, got {amount:g}."
        raise ValueError(msg)


class DebtService:
    """Persists one-off debt entries and payoff payments, and computes the running total."""

    def __init__(self, session_factory: SessionFactory):
        self._session_factory = session_factory

    def list_entries(self) -> list[DebtValues]:
        with self._session_factory() as session:
            statement = select(DebtEntry).order_by(
                DebtEntry.created_at.desc(), DebtEntry.id.desc()
            )
            return [_to_debt_values(row) for row in session.scalars(statement)]

    def create_entry(self, description: str, amount: float) -> DebtValues:
        _validate_debt(description, amount)
        with self._session_factory() as session:
            row = DebtEntry(description=description.strip(), amount=amount)
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_debt_values(row)

    def update_entry(self, debt_id: int, description: str, amount: float) -> DebtValues:
        _validate_debt(description, amount)
        with self._session_factory() as session:
            row = session.get(DebtEntry, debt_id)
            if row is None:
                raise DebtNotFoundError(debt_id)
            row.description = description.strip()
            row.amount = amount
            row.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            return _to_debt_values(row)

    def delete_entry(self, debt_id: int) -> None:
        with self._session_factory() as session:
            row = session.get(DebtEntry, debt_id)
            if row is None:
                raise DebtNotFoundError(debt_id)
            session.delete(row)
            session.commit()

    def total_entries_amount(self) -> float:
        with self._session_factory() as session:
            statement = select(func.coalesce(func.sum(DebtEntry.amount), 0.0))
            return float(session.scalar(statement) or 0.0)

    def total_paid_points(self) -> float:
        with self._session_factory() as session:
            statement = select(func.coalesce(func.sum(DebtPayment.amount_points), 0.0))
            return float(session.scalar(statement) or 0.0)

    def total_debt(self) -> float:
        """Outstanding debt: total entries minus total payments, clamped at 0."""
        return max(0.0, self.total_entries_amount() - self.total_paid_points())

    def recent_payments(self, limit: int = 20) -> list[DebtPaymentValues]:
        with self._session_factory() as session:
            statement = select(DebtPayment).order_by(DebtPayment.paid_at.desc()).limit(limit)
            return [_to_payment_values(row) for row in session.scalars(statement)]

    def pay_off(self, amount_points: float, available_points: float) -> DebtPaymentValues:
        """Pay off up to `amount_points` of the outstanding debt.

        The payment is capped to the remaining outstanding debt (paying more than is
        owed simply pays off exactly what's owed). Raises `ValueError` if
        `amount_points` is not positive, `NoDebtToPayError` if there is nothing
        outstanding, or `InsufficientPointsError` if `available_points` cannot cover
        the (possibly capped) payment.
        """
        if amount_points <= 0:
            msg = f"Payment amount must be greater than 0, got {amount_points:g}."
            raise ValueError(msg)
        outstanding = self.total_debt()
        if outstanding <= 0:
            raise NoDebtToPayError()
        payment_amount = min(amount_points, outstanding)
        if payment_amount > available_points:
            raise InsufficientPointsError(payment_amount, available_points)
        with self._session_factory() as session:
            payment = DebtPayment(amount_points=payment_amount)
            session.add(payment)
            session.commit()
            session.refresh(payment)
            return _to_payment_values(payment)

    def snapshot(self, available_points: float, *, recent_limit: int = 10) -> DebtSnapshot:
        return DebtSnapshot(
            entries=self.list_entries(),
            recent_payments=self.recent_payments(limit=recent_limit),
            total_debt=self.total_debt(),
            total_paid_points=self.total_paid_points(),
            available_points=available_points,
        )
