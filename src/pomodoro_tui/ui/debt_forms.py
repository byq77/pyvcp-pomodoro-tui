"""Asciimatics form-based modals for the debt screen.

These mirror `reward_forms.py`: each helper builds a small modal `Frame`, runs
it standalone with `Screen.play`, and returns the collected result once the
user confirms or cancels (a `Button` handler raises `StopApplication`, which
`Screen.play` catches and uses to return control to the caller).
"""

from __future__ import annotations
from dataclasses import dataclass
from asciimatics.exceptions import InvalidFields, StopApplication
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.widgets import Button, Frame, Layout, Text


@dataclass(slots=True)
class DebtFormResult:
    """Validated description/amount pair collected from the debt create/edit form."""

    description: str
    amount: float


@dataclass(slots=True)
class PayoffFormResult:
    """Validated points amount collected from the debt payoff form."""

    amount_points: float


def _validate_description(value: str) -> bool:
    return bool(value.strip())


def _validate_amount(value: str) -> bool:
    try:
        return float(value) > 0
    except ValueError:
        return False


class DebtFormFrame(Frame):
    """Modal form for creating or editing a debt entry's description and amount."""

    def __init__(
        self, screen: Screen, *, title: str, initial_description: str, initial_amount: str
    ):
        super().__init__(
            screen,
            height=9,
            width=min(50, screen.width - 4),
            title=title,
            is_modal=True,
        )
        self.result: DebtFormResult | None = None

        fields_layout = Layout([100], fill_frame=True)
        self.add_layout(fields_layout)
        fields_layout.add_widget(
            Text(label="Description:", name="description", validator=_validate_description)
        )
        fields_layout.add_widget(Text(label="Amount:", name="amount", validator=_validate_amount))

        buttons_layout = Layout([1, 1])
        self.add_layout(buttons_layout)
        buttons_layout.add_widget(Button("Save", self._on_save), 0)
        buttons_layout.add_widget(Button("Cancel", self._on_cancel), 1)

        self.data = {"description": initial_description, "amount": initial_amount}
        self.fix()

    def _on_save(self) -> None:
        try:
            self.save(validate=True)
        except InvalidFields:
            return
        self.result = DebtFormResult(
            description=self.data["description"].strip(), amount=float(self.data["amount"])
        )
        raise StopApplication("debt form saved")

    def _on_cancel(self) -> None:
        raise StopApplication("debt form cancelled")


class PayoffFormFrame(Frame):
    """Modal form for choosing how many points to pay off the outstanding debt."""

    def __init__(self, screen: Screen, *, total_debt: float, available: float):
        super().__init__(
            screen,
            height=10,
            width=min(50, screen.width - 4),
            title="Pay Off Debt",
            is_modal=True,
        )
        self.result: PayoffFormResult | None = None

        info_layout = Layout([100])
        self.add_layout(info_layout)
        info_layout.add_widget(Text(label="Total debt:", name="total_debt", readonly=True))
        info_layout.add_widget(Text(label="Available:", name="available", readonly=True))

        fields_layout = Layout([100], fill_frame=True)
        self.add_layout(fields_layout)
        fields_layout.add_widget(Text(label="Amount:", name="amount", validator=_validate_amount))

        buttons_layout = Layout([1, 1])
        self.add_layout(buttons_layout)
        buttons_layout.add_widget(Button("Pay", self._on_pay), 0)
        buttons_layout.add_widget(Button("Cancel", self._on_cancel), 1)

        self.data = {
            "total_debt": f"{total_debt:g}",
            "available": f"{available:g}",
            "amount": f"{min(total_debt, available):g}",
        }
        self.fix()

    def _on_pay(self) -> None:
        try:
            self.save(validate=True)
        except InvalidFields:
            return
        self.result = PayoffFormResult(amount_points=float(self.data["amount"]))
        raise StopApplication("payoff form confirmed")

    def _on_cancel(self) -> None:
        raise StopApplication("payoff form cancelled")


def run_debt_form(
    screen: Screen, *, title: str, initial_description: str = "", initial_amount: str = ""
) -> DebtFormResult | None:
    """Run the create/edit debt modal and return the result, or None if cancelled."""
    frame = DebtFormFrame(
        screen,
        title=title,
        initial_description=initial_description,
        initial_amount=initial_amount,
    )
    screen.play([Scene([frame], -1)], stop_on_resize=True)
    return frame.result


def run_payoff_form(
    screen: Screen, *, total_debt: float, available: float
) -> PayoffFormResult | None:
    """Run the debt payoff modal and return the result, or None if cancelled."""
    frame = PayoffFormFrame(screen, total_debt=total_debt, available=available)
    screen.play([Scene([frame], -1)], stop_on_resize=True)
    return frame.result
