"""Mark a queued (planned) print complete.

Pre-fills every field with the planned values so only the actuals that changed
need touching — real prints often deviate from the plan on weight, time or the
agreed price. Accepting writes those actuals back and flips the order's status
to "completed", at which point it starts counting towards the dashboard.
"""
from __future__ import annotations

from dataclasses import replace

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QVBoxLayout,
)

from .. import calculations as calc
from ..models import Order
from .widgets import (
    DurationEditor,
    field_label,
    fmt_money,
    money_spin,
    plain_double_spin,
    section_label,
)


class MarkCompleteDialog(QDialog):
    def __init__(self, order: Order, settings: dict, parent=None):
        super().__init__(parent)
        self.order = order
        self.settings = settings
        self.per_plate = order.pricing_mode == "per_plate"
        self.setWindowTitle("Mark complete")
        self.setMinimumWidth(540)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 18)
        outer.setSpacing(14)

        title = (order.title or "").strip() or "(untitled)"
        customer = (order.customer_name or "").strip() or "(no customer)"
        head = QLabel(
            f"Completing <b>{title}</b> for <b>{customer}</b>.<br>"
            "Adjust any actuals that differed from the plan, then confirm.")
        head.setWordWrap(True)
        head.setObjectName("DialogNote")
        outer.addWidget(head)

        outer.addWidget(section_label("Plates"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        headers = ["Plate", "Weight", "Time"] + (["Price"] if self.per_plate else [])
        for c, text in enumerate(headers):
            grid.addWidget(field_label(text), 0, c)

        # Each entry: (plate, weight_spin, duration_editor, price_spin|None)
        self._rows: list = []
        for r, plate in enumerate(order.plates, start=1):
            weight = plain_double_spin(0, 100_000, decimals=2, step=1, suffix=" g")
            weight.setValue(plate.weight_grams)
            weight.valueChanged.connect(self._recompute)
            duration = DurationEditor()
            duration.set_minutes(plate.print_time_minutes)
            duration.valueChanged.connect(self._recompute)
            grid.addWidget(QLabel(plate.plate_label or f"Plate {r}"), r, 0)
            grid.addWidget(weight, r, 1)
            grid.addWidget(duration, r, 2)
            price = None
            if self.per_plate:
                price = money_spin(minimum=0, maximum=100_000_000)
                price.setValue(plate.final_price or 0.0)
                price.valueChanged.connect(self._recompute)
                grid.addWidget(price, r, 3)
            self._rows.append((plate, weight, duration, price))
        outer.addLayout(grid)

        # Order-level pricing has a single final price for the whole order.
        self.final_spin = None
        if not self.per_plate:
            price_row = QGridLayout()
            price_row.addWidget(field_label("Final price"), 0, 0)
            self.final_spin = money_spin(minimum=0, maximum=100_000_000)
            self.final_spin.setValue(calc.resolved_order_level_price(order, settings))
            self.final_spin.valueChanged.connect(self._recompute)
            price_row.addWidget(self.final_spin, 0, 1)
            price_row.setColumnStretch(2, 1)
            outer.addLayout(price_row)

        self.summary = QLabel("")
        self.summary.setObjectName("FormulaHint")
        outer.addWidget(self.summary)

        buttons = QDialogButtonBox()
        ok = buttons.addButton("Mark complete", QDialogButtonBox.AcceptRole)
        ok.setObjectName("PrimaryButton")
        cancel = buttons.addButton(QDialogButtonBox.Cancel)
        cancel.setObjectName("SecondaryButton")
        ok.clicked.connect(self._on_accept)
        cancel.clicked.connect(self.reject)
        outer.addWidget(buttons)

        self._recompute()

    def _live_cogs(self) -> tuple[float, list[float]]:
        """Per-run COGS from the current field values, using each plate's rate
        snapshot (one run of the plate set — quantity is applied by callers).

        Returns (total, per-plate list) so callers can attribute per plate.
        """
        per = [
            calc.plate_cogs(replace(plate, weight_grams=weight.value(),
                                     print_time_minutes=duration.minutes(),
                                     failed_attempts=plate.failed_attempts))
            + calc.plate_failed_cost(plate)
            for plate, weight, duration, _price in self._rows
        ]
        return sum(per), per

    def _live_price(self) -> float:
        """Per-run price: the order-level field already is (it mirrors
        resolved_order_level_price, which is whole-job); in per_plate mode
        it's the sum of each plate's own per-run price."""
        if self.per_plate:
            return sum(p.value() for _pl, _w, _d, p in self._rows if p is not None)
        return self.final_spin.value()

    def _recompute(self) -> None:
        cogs_per_run, _ = self._live_cogs()
        qty = self.order.quantity
        cogs_whole = cogs_per_run * qty
        price_whole = self._live_price() * qty if self.per_plate else self._live_price()
        profit_whole = price_whole - cogs_whole
        note = f"   ·   whole job ×{qty}" if qty > 1 else ""
        self.summary.setText(
            f"COGS {fmt_money(cogs_whole)}   ·   Price {fmt_money(price_whole)}   ·   "
            f"Profit {fmt_money(profit_whole)}{note}")

    def _on_accept(self) -> None:
        cogs_per_run, per = self._live_cogs()
        for (plate, weight, duration, price), pcogs in zip(self._rows, per):
            plate.weight_grams = round(weight.value(), 2)
            plate.print_time_minutes = duration.minutes()
            if self.per_plate and price is not None:
                # Per-run values, exactly as entered — quantity is applied
                # only when the order rolls these up (calc.order_final_price
                # / calc.order_profit), never stored on the plate itself.
                plate.final_price = round(price.value(), 2)
                plate.profit = round(price.value() - pcogs, 2)
        if not self.per_plate:
            price_whole = round(self.final_spin.value(), 2)
            self.order.final_price = price_whole
            self.order.profit = round(price_whole - cogs_per_run * self.order.quantity, 2)
        self.order.status = "completed"
        self.accept()
