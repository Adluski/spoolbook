"""Read-only cost breakdown for one order.

Opens from the order-entry footer's "Breakdown" button and from the
right-click menu in History/Queue, always for an Order object the caller
already holds — it never touches the database. Everything shown is derived
from calculations.py; no arithmetic lives here, and no per-plate revenue or
profit is ever shown (revenue/profit are order-level facts, reported once in
the TOTALS section). Failed-attempt figures use each plate's own snapshotted
rates, never live settings.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import calculations as calc
from ..config import MATERIAL_SOURCE_LABELS
from ..models import Order
from .widgets import fmt_grams, fmt_minutes, fmt_money, hline, section_label


def _rate_per_gram(rate: float) -> str:
    return f"{fmt_money(rate)}/g"


def _rate_per_hour(rate: float) -> str:
    return f"{fmt_money(rate)}/h"


class CostBreakdownDialog(QDialog):
    def __init__(self, order: Order, settings: dict, parent=None):
        super().__init__(parent)
        self.order = order
        self.settings = settings
        self.qty = order.quantity
        self.setWindowTitle("Cost breakdown")
        self.setMinimumWidth(560)
        self.setMinimumHeight(480)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 18)
        outer.setSpacing(12)

        outer.addLayout(self._build_header())

        scroll = QScrollArea()
        scroll.setObjectName("BodyScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        self._body = QVBoxLayout(body)
        self._body.setContentsMargins(0, 0, 4, 0)
        self._body.setSpacing(18)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self._build_delivered()
        self._build_failed()
        self._build_totals()
        self._build_material_time()
        self._body.addStretch(1)

        buttons = QDialogButtonBox()
        close = buttons.addButton("Close", QDialogButtonBox.RejectRole)
        close.setObjectName("SecondaryButton")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.reject)
        outer.addWidget(buttons)

    # -- header -------------------------------------------------------------
    def _build_header(self) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(2)
        title = (self.order.title or "").strip() or "(untitled)"
        customer = (self.order.customer_name or "").strip() or "(no customer)"
        head = QLabel(f"Cost breakdown — <b>{title}</b> for <b>{customer}</b>")
        head.setObjectName("PageTitle")
        head.setWordWrap(True)
        mode = ("Per-plate pricing" if self.order.pricing_mode == "per_plate"
                else "Order-level pricing")
        sub = QLabel(f"Quantity: {self.qty} · {mode}")
        sub.setObjectName("PageSubtitle")
        box.addWidget(head)
        box.addWidget(sub)
        return box

    # -- shared row helpers -------------------------------------------------
    def _num(self, text: str, strong: bool = False, tone: str = "") -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("BreakdownNumStrong" if strong else "BreakdownNum")
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if tone:
            lbl.setProperty("tone", tone)
        return lbl

    def _detail(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("BreakdownDetail")
        return lbl

    def _new_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(0, 1)
        return grid

    def _span_line(self, grid: QGridLayout, r: int, cols: int) -> None:
        grid.addWidget(hline(), r, 0, 1, cols)

    # -- Section 1: delivered plates ---------------------------------------
    def _build_delivered(self) -> None:
        self._body.addWidget(section_label("Delivered plates"))
        grid = self._new_grid()
        two_col = self.qty > 1
        ncols = 3 if two_col else 2
        r = 0
        if two_col:
            grid.addWidget(self._col_head("per run"), r, 1, Qt.AlignRight)
            grid.addWidget(self._col_head(f"× {self.qty}"), r, 2, Qt.AlignRight)
            r += 1

        for plate in self.order.plates:
            source = MATERIAL_SOURCE_LABELS.get(plate.material_source,
                                                plate.material_source)
            head = QLabel(
                f"<b>{plate.plate_label or 'Plate'}</b> &nbsp; "
                f"<span>{plate.material_type} · {source}</span> &nbsp; "
                f"<span>{fmt_grams(plate.weight_grams)} · "
                f"{fmt_minutes(plate.print_time_minutes)}</span>")
            head.setObjectName("BreakdownPlate")
            grid.addWidget(head, r, 0, 1, ncols)
            r += 1

            mat = calc.plate_material_cost(plate)
            mach = calc.plate_machine_cost(plate)
            cogs = calc.plate_cogs(plate)

            if plate.material_source == "customer":
                mat_detail = f"    material  {fmt_grams(plate.weight_grams)} (supplied)"
            else:
                mat_detail = (f"    material  {fmt_grams(plate.weight_grams)} × "
                              f"{_rate_per_gram(plate.material_rate_per_gram)}")
            r = self._money_row(grid, r, mat_detail, mat, two_col)

            mach_detail = (f"    machine   {fmt_minutes(plate.print_time_minutes)} × "
                           f"{_rate_per_hour(plate.machine_rate_per_hour)}")
            r = self._money_row(grid, r, mach_detail, mach, two_col)
            r = self._money_row(grid, r, "    plate COGS", cogs, two_col, strong=False)

        self._span_line(grid, r, ncols)
        r += 1
        per_run = calc.total_cogs(self.order.plates)
        r = self._money_row(grid, r, "Delivered COGS", per_run, two_col, strong=True)
        self._add_grid(grid)

    def _money_row(self, grid, r, detail, per_run, two_col, strong=False) -> int:
        grid.addWidget(self._detail(detail), r, 0)
        grid.addWidget(self._num(fmt_money(per_run), strong=strong), r, 1)
        if two_col:
            grid.addWidget(self._num(fmt_money(per_run * self.qty), strong=strong), r, 2)
        return r + 1

    # -- Section 2: failed attempts ----------------------------------------
    def _build_failed(self) -> None:
        attempts = [(p, a) for p in self.order.plates for a in p.failed_attempts]
        if not attempts:
            return
        header = QLabel("FAILED ATTEMPTS")
        header.setObjectName("SectionLabel")
        note = QLabel("logged once — not multiplied by quantity")
        note.setObjectName("BreakdownMeta")
        cap = QWidget()
        capl = QVBoxLayout(cap)
        capl.setContentsMargins(0, 0, 0, 0)
        capl.setSpacing(1)
        capl.addWidget(header)
        capl.addWidget(note)
        self._body.addWidget(cap)

        grid = self._new_grid()
        r = 0
        for plate, attempt in attempts:
            fmat = calc.failed_attempt_material_cost(plate, attempt)
            fmach = calc.failed_attempt_machine_cost(plate, attempt)
            pct = attempt.completion_percent
            grams = plate.weight_grams * pct / 100.0
            mins = plate.print_time_minutes * pct / 100.0

            head = QLabel(
                f"<b>{plate.plate_label or 'Plate'}</b> &nbsp; "
                f"<span>failed at {pct:g}%</span> &nbsp; "
                f"<span>{grams:.1f} g · {fmt_minutes(mins)}</span>")
            head.setObjectName("BreakdownPlate")
            grid.addWidget(head, r, 0, 1, 2)
            r += 1

            if plate.material_source == "customer":
                mat_detail = f"    material  {grams:.1f} g (supplied)"
            else:
                mat_detail = (f"    material  {grams:.1f} g × "
                              f"{_rate_per_gram(plate.material_rate_per_gram)}")
            grid.addWidget(self._detail(mat_detail), r, 0)
            grid.addWidget(self._num(fmt_money(fmat)), r, 1)
            r += 1
            mach_detail = (f"    machine   {fmt_minutes(mins)} × "
                           f"{_rate_per_hour(plate.machine_rate_per_hour)}")
            grid.addWidget(self._detail(mach_detail), r, 0)
            grid.addWidget(self._num(fmt_money(fmach)), r, 1)
            r += 1
            self._span_line(grid, r, 2)
            r += 1
            grid.addWidget(self._detail(
                f"Wasted   {grams:.1f} g · {fmt_minutes(mins)}"), r, 0)
            grid.addWidget(self._num(fmt_money(fmat + fmach), strong=True), r, 1)
            r += 1
        self._add_grid(grid)

    # -- Section 3: totals --------------------------------------------------
    def _build_totals(self) -> None:
        self._body.addWidget(section_label("Totals"))
        grid = self._new_grid()
        per_run = calc.total_cogs(self.order.plates)
        delivered_whole = per_run * self.qty
        wasted = calc.total_failed_cost(self.order.plates)
        total = calc.total_cogs_for_order(self.order)
        revenue = calc.order_final_price(self.order, self.settings)
        profit = calc.order_profit(self.order, self.settings)
        margin = calc.margin_percent(revenue, profit)

        r = 0
        delivered_label = "Delivered COGS"
        if self.qty > 1:
            delivered_label += f" ({fmt_money(per_run)} × {self.qty})"
        grid.addWidget(self._detail(delivered_label), r, 0)
        grid.addWidget(self._num(fmt_money(delivered_whole)), r, 1)
        r += 1
        grid.addWidget(self._detail("Wasted"), r, 0)
        grid.addWidget(self._num(fmt_money(wasted)), r, 1)
        r += 1
        self._span_line(grid, r, 2)
        r += 1
        grid.addWidget(self._detail("TOTAL COGS"), r, 0)
        grid.addWidget(self._num(fmt_money(total), strong=True), r, 1)
        r += 1
        grid.addWidget(self._detail("Revenue"), r, 0)
        grid.addWidget(self._num(fmt_money(revenue)), r, 1)
        r += 1
        grid.addWidget(self._detail("Profit"), r, 0)
        tone = "positive" if profit >= 0 else "negative"
        grid.addWidget(self._num(f"{fmt_money(profit)}   ({margin:.1f}%)",
                                 strong=True, tone=tone), r, 1)
        self._add_grid(grid)

    # -- Section 4: material & time ----------------------------------------
    def _build_material_time(self) -> None:
        self._body.addWidget(section_label("Material & time"))
        grid = self._new_grid()
        own = calc.total_consumed_grams(self.order, "own")
        supplied = calc.total_consumed_grams(self.order, "customer")
        total_g = calc.total_consumed_grams(self.order, None)
        total_m = calc.total_consumed_minutes(self.order)
        paid = calc.whole_job_material_cost(self.order)

        r = self._mt_row(grid, 0, "Own filament", fmt_grams(own),
                         f"(paid: {fmt_money(paid)})")
        r = self._mt_row(grid, r, "Customer-supplied", fmt_grams(supplied),
                         f"(paid: {fmt_money(0.0)})")
        r = self._mt_row(grid, r, "Total consumed", fmt_grams(total_g), "")
        r = self._mt_row(grid, r, "Total print time", fmt_minutes(total_m), "")
        self._add_grid(grid)

    def _mt_row(self, grid, r, label, value, note) -> int:
        grid.addWidget(self._detail(label), r, 0)
        grid.addWidget(self._num(value), r, 1)
        if note:
            n = QLabel(note)
            n.setObjectName("BreakdownMeta")
            grid.addWidget(n, r, 2)
        return r + 1

    # -- layout glue --------------------------------------------------------
    def _col_head(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("BreakdownColHead")
        return lbl

    def _add_grid(self, grid: QGridLayout) -> None:
        wrap = QWidget()
        wrap.setLayout(grid)
        self._body.addWidget(wrap)
