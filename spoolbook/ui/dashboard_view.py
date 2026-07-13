"""Dashboard: revenue / profit / COGS for a date range, split by material.

Revenue and profit are attributed down to each plate (exactly in per-plate
mode; by COGS share in order-level mode) so the material breakdown is
meaningful regardless of how each order was priced.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import calculations as calc
from ..config import MATERIALS
from .theme import NEGATIVE, POSITIVE
from .widgets import PageHeader, Panel, fmt_grams, fmt_money, section_label

MAT_COLUMNS = ["Material", "Plates", "Weight", "COGS", "Revenue", "Profit", "Margin"]


class DashboardView(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._ready = False
        self._metrics: dict[str, QLabel] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = QFrame()
        top.setObjectName("TopBar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(32, 20, 32, 12)
        tl.addWidget(PageHeader("Dashboard", "Revenue, profit and cost at a glance."))
        tl.addStretch(1)
        tl.addWidget(self._build_range_controls())
        outer.addWidget(top)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(32, 16, 32, 20)
        bl.setSpacing(18)
        bl.addWidget(self._build_metrics())
        bl.addWidget(self._build_material_panel(), 1)
        outer.addWidget(body, 1)

        self._ready = True
        self.refresh()

    # -- range controls -----------------------------------------------------
    def _build_range_controls(self) -> QWidget:
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.preset = QComboBox()
        for label in ("All time", "This month", "Last 30 days",
                      "This year", "Custom range"):
            self.preset.addItem(label)
        self.preset.currentIndexChanged.connect(self._on_preset_changed)
        lay.addWidget(self.preset)

        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDisplayFormat("dd MMM yyyy")
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        self.from_date.dateChanged.connect(self.refresh)
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDisplayFormat("dd MMM yyyy")
        self.to_date.setDate(QDate.currentDate())
        self.to_date.dateChanged.connect(self.refresh)
        dash = QLabel("→")
        dash.setObjectName("Muted")
        lay.addWidget(self.from_date)
        lay.addWidget(dash)
        lay.addWidget(self.to_date)

        self._on_preset_changed()
        return wrap

    def _on_preset_changed(self) -> None:
        custom = self.preset.currentText() == "Custom range"
        self.from_date.setEnabled(custom)
        self.to_date.setEnabled(custom)
        self.refresh()

    def _range(self):
        preset = self.preset.currentText()
        today = datetime.now()
        end = datetime.combine(today.date(), time(23, 59, 59))
        if preset == "All time":
            return None, None
        if preset == "This month":
            return today.replace(day=1, hour=0, minute=0, second=0, microsecond=0), end
        if preset == "Last 30 days":
            return datetime.combine((today - timedelta(days=30)).date(), time()), end
        if preset == "This year":
            return today.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0), end
        f, t = self.from_date.date(), self.to_date.date()
        return (datetime(f.year(), f.month(), f.day()),
                datetime.combine(datetime(t.year(), t.month(), t.day()), time(23, 59, 59)))

    # -- metric blocks ------------------------------------------------------
    def _build_metrics(self) -> QWidget:
        wrap = QWidget()
        grid = QGridLayout(wrap)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        specs = [
            ("revenue", "Revenue", "MetricValueAccent"),
            ("cogs", "Total COGS", "MetricValue"),
            ("profit", "Profit", "MetricValue"),
            ("margin", "Margin", "MetricValue"),
            ("orders", "Orders", "MetricValue"),
        ]
        for col, (key, caption, value_name) in enumerate(specs):
            panel = Panel()
            pl = QVBoxLayout(panel)
            pl.setContentsMargins(18, 14, 18, 14)
            pl.setSpacing(4)
            cap = QLabel(caption.upper())
            cap.setObjectName("StatCaption")
            value = QLabel("—")
            value.setObjectName(value_name)
            pl.addWidget(cap)
            pl.addWidget(value)
            grid.addWidget(panel, 0, col)
            grid.setColumnStretch(col, 1)
            self._metrics[key] = value
        return wrap

    def _build_material_panel(self) -> Panel:
        panel = Panel()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(22, 16, 22, 18)
        lay.setSpacing(10)
        lay.addWidget(section_label("By material"))

        self.table = QTableWidget(0, len(MAT_COLUMNS))
        self.table.setObjectName("MaterialTable")
        self.table.setHorizontalHeaderLabels(MAT_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(MAT_COLUMNS)):
            header.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        lay.addWidget(self.table)

        self.empty_label = QLabel("No orders in this range.")
        self.empty_label.setObjectName("Muted")
        self.empty_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty_label)
        return panel

    # -- data ---------------------------------------------------------------
    def refresh(self) -> None:
        if not self._ready:
            return
        settings = self.db.get_settings()
        start, end = self._range()
        # Only realized orders count towards revenue/profit/COGS; queued
        # (planned) prints are excluded entirely.
        orders = self.db.list_orders(start=start, end=end, status="completed")

        revenue = profit = cogs = 0.0
        by_mat = {m: {"plates": 0, "weight": 0.0, "cogs": 0.0,
                      "revenue": 0.0, "profit": 0.0} for m in MATERIALS}
        extra = defaultdict(lambda: {"plates": 0, "weight": 0.0, "cogs": 0.0,
                                     "revenue": 0.0, "profit": 0.0})

        for order in orders:
            rollup = calc.order_rollup(order, settings)
            revenue += rollup["final_price"]
            profit += rollup["profit"]
            cogs += rollup["total_cogs_for_order"]
            for attr, plate in zip(calc.plate_attributions(order, settings), order.plates):
                bucket = by_mat.get(attr["material_type"]) or extra[attr["material_type"]]
                bucket["plates"] += 1
                bucket["weight"] += plate.weight_grams
                bucket["cogs"] += attr["cogs"]
                bucket["revenue"] += attr["revenue"]
                bucket["profit"] += attr["profit"]

        self._metrics["revenue"].setText(fmt_money(revenue))
        self._metrics["cogs"].setText(fmt_money(cogs))
        self._metrics["profit"].setText(fmt_money(profit))
        self._tone(self._metrics["profit"], profit >= 0)
        self._metrics["margin"].setText(f"{calc.margin_percent(revenue, profit):.1f}%")
        self._metrics["orders"].setText(str(len(orders)))

        rows = [(m, by_mat[m]) for m in MATERIALS] + list(extra.items())
        rows = [(m, d) for m, d in rows if d["plates"] > 0]
        self._populate_table(rows, revenue, profit, cogs)

        has_data = bool(orders)
        self.table.setVisible(has_data)
        self.empty_label.setVisible(not has_data)

    def _populate_table(self, rows, tot_rev, tot_profit, tot_cogs) -> None:
        self.table.setRowCount(len(rows) + (1 if rows else 0))
        for r, (material, d) in enumerate(rows):
            self._set_row(r, material, d["plates"], d["weight"], d["cogs"],
                          d["revenue"], d["profit"], bold=False)
        if rows:
            total_plates = sum(d["plates"] for _, d in rows)
            total_weight = sum(d["weight"] for _, d in rows)
            self._set_row(len(rows), "All materials", total_plates, total_weight,
                          tot_cogs, tot_rev, tot_profit, bold=True)

    def _set_row(self, r, material, plates, weight, cogs, revenue, profit, bold) -> None:
        margin = calc.margin_percent(revenue, profit)
        cells = [
            (material, Qt.AlignLeft),
            (str(plates), Qt.AlignRight),
            (fmt_grams(weight), Qt.AlignRight),
            (fmt_money(cogs), Qt.AlignRight),
            (fmt_money(revenue), Qt.AlignRight),
            (fmt_money(profit), Qt.AlignRight),
            (f"{margin:.1f}%", Qt.AlignRight),
        ]
        for c, (text, align) in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setTextAlignment(align | Qt.AlignVCenter)
            if bold:
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            if c == 5:  # profit column tone
                item.setForeground(QBrush(QColor(POSITIVE if profit >= 0 else NEGATIVE)))
            self.table.setItem(r, c, item)

    def _tone(self, label, positive) -> None:
        label.setProperty("tone", "positive" if positive else "negative")
        label.style().unpolish(label)
        label.style().polish(label)

    def on_settings_changed(self) -> None:
        self.refresh()
