"""Asciimatics form-based modals for the rewards screen.

These are the only pieces of the UI that use asciimatics' `Frame`/`Widget`
system; the rest of `PomodoroTUI` draws directly via `Screen.print_at`. Each
helper here builds a small modal `Frame`, runs it standalone with
`Screen.play`, and returns the collected result once the user confirms or
cancels (a `Button` handler raises `StopApplication`, which `Screen.play`
catches and uses to return control to the caller).
"""

from __future__ import annotations
from dataclasses import dataclass
from asciimatics.exceptions import InvalidFields, StopApplication
from asciimatics.scene import Scene
from asciimatics.screen import Screen
from asciimatics.widgets import Button, Frame, Layout, PopUpDialog, Text


@dataclass(slots=True)
class RewardFormResult:
    """Validated name/cost pair collected from the reward create/edit form."""

    name: str
    cost_points: float


@dataclass(slots=True)
class PurchaseFormResult:
    """Validated quantity collected from the purchase form."""

    quantity: int


def _validate_name(value: str) -> bool:
    return bool(value.strip())


def _validate_cost(value: str) -> bool:
    try:
        return float(value) > 0
    except ValueError:
        return False


def _validate_quantity(value: str) -> bool:
    try:
        return int(value) >= 1
    except ValueError:
        return False


class RewardFormFrame(Frame):
    """Modal form for creating or editing a reward's name and cost."""

    def __init__(self, screen: Screen, *, title: str, initial_name: str, initial_cost: str):
        super().__init__(
            screen,
            height=9,
            width=min(50, screen.width - 4),
            title=title,
            is_modal=True,
        )
        self.result: RewardFormResult | None = None

        fields_layout = Layout([100], fill_frame=True)
        self.add_layout(fields_layout)
        fields_layout.add_widget(Text(label="Name:", name="name", validator=_validate_name))
        fields_layout.add_widget(Text(label="Cost (pts):", name="cost", validator=_validate_cost))

        buttons_layout = Layout([1, 1])
        self.add_layout(buttons_layout)
        buttons_layout.add_widget(Button("Save", self._on_save), 0)
        buttons_layout.add_widget(Button("Cancel", self._on_cancel), 1)

        self.data = {"name": initial_name, "cost": initial_cost}
        self.fix()

    def _on_save(self) -> None:
        try:
            self.save(validate=True)
        except InvalidFields:
            return
        self.result = RewardFormResult(
            name=self.data["name"].strip(), cost_points=float(self.data["cost"])
        )
        raise StopApplication("reward form saved")

    def _on_cancel(self) -> None:
        raise StopApplication("reward form cancelled")


class PurchaseFormFrame(Frame):
    """Modal form for choosing how many units of a reward to buy."""

    def __init__(self, screen: Screen, *, reward_name: str, unit_cost: float, available: float):
        super().__init__(
            screen,
            height=10,
            width=min(50, screen.width - 4),
            title=f"Buy '{reward_name}'",
            is_modal=True,
        )
        self.result: PurchaseFormResult | None = None

        info_layout = Layout([100])
        self.add_layout(info_layout)
        info_layout.add_widget(Text(label="Unit cost:", name="unit_cost", readonly=True))
        info_layout.add_widget(Text(label="Available:", name="available", readonly=True))

        fields_layout = Layout([100], fill_frame=True)
        self.add_layout(fields_layout)
        fields_layout.add_widget(
            Text(label="Quantity:", name="quantity", validator=_validate_quantity)
        )

        buttons_layout = Layout([1, 1])
        self.add_layout(buttons_layout)
        buttons_layout.add_widget(Button("Buy", self._on_buy), 0)
        buttons_layout.add_widget(Button("Cancel", self._on_cancel), 1)

        self.data = {
            "unit_cost": f"{unit_cost:g}",
            "available": f"{available:g}",
            "quantity": "1",
        }
        self.fix()

    def _on_buy(self) -> None:
        try:
            self.save(validate=True)
        except InvalidFields:
            return
        self.result = PurchaseFormResult(quantity=int(self.data["quantity"]))
        raise StopApplication("purchase form confirmed")

    def _on_cancel(self) -> None:
        raise StopApplication("purchase form cancelled")


def run_reward_form(
    screen: Screen, *, title: str, initial_name: str = "", initial_cost: str = ""
) -> RewardFormResult | None:
    """Run the create/edit reward modal and return the result, or None if cancelled."""
    frame = RewardFormFrame(
        screen, title=title, initial_name=initial_name, initial_cost=initial_cost
    )
    screen.play([Scene([frame], -1)], stop_on_resize=True)
    return frame.result


def run_purchase_form(
    screen: Screen, *, reward_name: str, unit_cost: float, available: float
) -> PurchaseFormResult | None:
    """Run the purchase-quantity modal and return the result, or None if cancelled."""
    frame = PurchaseFormFrame(
        screen, reward_name=reward_name, unit_cost=unit_cost, available=available
    )
    screen.play([Scene([frame], -1)], stop_on_resize=True)
    return frame.result


def run_confirm_dialog(screen: Screen, message: str) -> bool:
    """Show a Yes/No confirmation dialog and return True if the user picked Yes."""
    choice: dict[str, bool] = {"confirmed": False}

    def _on_close(selected: int) -> None:
        choice["confirmed"] = selected == 0
        raise StopApplication("confirm dialog closed")

    dialog = PopUpDialog(screen, message, ["Yes", "No"], on_close=_on_close)
    screen.play([Scene([dialog], -1)], stop_on_resize=True)
    return choice["confirmed"]
