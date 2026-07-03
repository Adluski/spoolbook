"""Mark a queued (planned) print complete.

Pre-fills every field with the planned values so only the actuals that changed
need touching — real prints often deviate from the plan on weight, time or the
agreed price. Accepting writes those actuals back and flips the order's status
to "completed", at which point it starts counting towards the dashboard.
"""
from __future__ import annotations

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
        """COGS from the current field values, using each plate's rate snapshot.

        Returns (total, per-plate list) so callers can attribute per plate.
        """
        per = []
        for plate, weight, duration, _price in self._rows:
            material = 0.0 if plate.material_source == "customer" \
                else weight.value() * plate.material_rate_per_gram
            machine = (duration.minutes() / 60.0) * plate.machine_rate_per_hour
            per.append(material + machine)
        return sum(per), per

    def _live_price(self) -> float:
        if self.per_plate:
            return sum(p.value() for _pl, _w, _d, p in self._rows if p is not None)
        return self.final_spin.value()

    def _recompute(self) -> None:
        cogs, _ = self._live_cogs()
        price = self._live_price()
        self.summary.setText(
            f"COGS {fmt_money(cogs)}   ·   Price {fmt_money(price)}   ·   "
            f"Profit {fmt_money(price - cogs)}")

    def _on_accept(self) -> None:
        cogs, per = self._live_cogs()
        for (plate, weight, duration, price), pcogs in zip(self._rows, per):
            plate.weight_grams = round(weight.value(), 2)
            plate.print_time_minutes = duration.minutes()
            if self.per_plate and price is not None:
                plate.final_price = round(price.value(), 2)
                plate.profit = round(price.value() - pcogs, 2)
        if not self.per_plate:
            price = round(self.final_spin.value(), 2)
            self.order.final_price = price
            self.order.profit = round(price - cogs, 2)  # derived, kept in sync
        self.order.status = "completed"
        self.accept()
