"""History: every saved order as an expandable row over its plates.

Filterable by customer, date range, material and reprint status; sortable by
any column (numeric columns sort numerically). Right-click an order to edit or
delete it, or a plate to log a reprint.
"""
from __future__ import annotations

from datetime import datetime, time

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import calculations as calc
from ..csv_export import write_csv
from ..config import MATERIAL_SOURCE_LABELS, MATERIALS, PRICING_MODE_LABELS
from .theme import NEGATIVE, POSITIVE
from .widgets import PageHeader, fmt_grams, fmt_minutes, fmt_money

COLUMNS = ["Date · Plate", "Customer · Material", "Title · Source",
           "Weight", "Time", "COGS", "Price", "Profit", "Margin"]
NUMERIC_COLS = {3, 4, 5, 6, 7, 8}


class _Item(QTreeWidgetItem):
    """Tree item that sorts numeric columns by stored value, not text."""

    def __lt__(self, other: "_Item") -> bool:
        tree = self.treeWidget()
        col = tree.sortColumn() if tree else 0
        a = self.data(col, Qt.UserRole)
        b = other.data(col, Qt.UserRole)
        if a is not None and b is not None:
            return a < b
        return self.text(col) < other.text(col)


class HistoryView(QWidget):
    def __init__(self, db, window, parent=None):
        super().__init__(parent)
        self.db = db
        self.window = window

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = QFrame()
        top.setObjectName("TopBar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(32, 20, 32, 12)
        tl.addWidget(PageHeader("History", "Every saved order and its plates."))
        tl.addStretch(1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        tl.addWidget(self.count_label)
        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.clicked.connect(self._export_csv)
        tl.addWidget(self.export_btn)
        outer.addWidget(top)
        # Build the tree first (filter setup triggers a refresh that reads it),
        # but add the filter bar above it in the layout.
        tree_wrap = self._build_tree()
        outer.addWidget(self._build_filters())
        outer.addWidget(tree_wrap, 1)

        self.refresh()

    def _build_tree(self) -> QWidget:
        self.tree = QTreeWidget()
        self.tree.setObjectName("HistoryTree")
        self.tree.setColumnCount(len(COLUMNS))
        self.tree.setHeaderLabels(COLUMNS)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.DescendingOrder)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self.tree.itemDoubleClicked.connect(self._on_double_click)

        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        for c in range(3, len(COLUMNS)):
            header.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.tree.setColumnWidth(1, 150)

        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(32, 8, 32, 20)
        wl.addWidget(self.tree)
        return wrap

    # -- filters ------------------------------------------------------------
    def _build_filters(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("FilterBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(32, 10, 32, 10)
        lay.setSpacing(10)

        self.customer_edit = QLineEdit()
        self.customer_edit.setPlaceholderText("Filter by customer…")
        self.customer_edit.setClearButtonEnabled(True)
        self.customer_edit.setFixedWidth(200)
        self.customer_edit.textChanged.connect(self.refresh)
        lay.addWidget(self.customer_edit)

        self.date_check = QCheckBox("Date range")
        self.date_check.stateChanged.connect(self._on_date_toggle)
        lay.addWidget(self.date_check)

        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDisplayFormat("dd MMM yyyy")
        self.from_date.setDate(QDate.currentDate().addMonths(-12))
        self.from_date.dateChanged.connect(self.refresh)
        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDisplayFormat("dd MMM yyyy")
        self.to_date.setDate(QDate.currentDate())
        self.to_date.dateChanged.connect(self.refresh)
        lay.addWidget(self.from_date)
        dash = QLabel("→")
        dash.setObjectName("Muted")
        lay.addWidget(dash)
        lay.addWidget(self.to_date)

        self.material_combo = QComboBox()
        self.material_combo.addItem("All materials", None)
        for mt in MATERIALS:
            self.material_combo.addItem(mt, mt)
        self.material_combo.currentIndexChanged.connect(self.refresh)
        lay.addWidget(self.material_combo)

        self.reprint_check = QCheckBox("Reprints only")
        self.reprint_check.stateChanged.connect(self.refresh)
        lay.addWidget(self.reprint_check)

        lay.addStretch(1)

        clear = QPushButton("Clear")
        clear.setObjectName("SecondaryButton")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(self._clear_filters)
        lay.addWidget(clear)

        self._on_date_toggle()
        return bar

    def _on_date_toggle(self) -> None:
        on = self.date_check.isChecked()
        self.from_date.setEnabled(on)
        self.to_date.setEnabled(on)
        self.refresh()

    def _clear_filters(self) -> None:
        self.customer_edit.blockSignals(True)
        self.customer_edit.clear()
        self.customer_edit.blockSignals(False)
        self.material_combo.setCurrentIndex(0)
        self.reprint_check.setChecked(False)
        self.date_check.setChecked(False)
        self.refresh()

    def _current_filters(self) -> dict:
        filters: dict = {}
        text = self.customer_edit.text().strip()
        if text:
            filters["customer"] = text
        if self.date_check.isChecked():
            f = self.from_date.date()
            t = self.to_date.date()
            filters["start"] = datetime(f.year(), f.month(), f.day())
            filters["end"] = datetime.combine(
                datetime(t.year(), t.month(), t.day()), time(23, 59, 59))
        material = self.material_combo.currentData()
        if material:
            filters["material"] = material
        if self.reprint_check.isChecked():
            filters["reprint_only"] = True
        return filters

    # -- population ---------------------------------------------------------
    def refresh(self) -> None:
        settings = self.db.get_settings()
        orders = self.db.list_orders(**self._current_filters())

        self.tree.setSortingEnabled(False)
        self.tree.clear()
        for order in orders:
            self.tree.addTopLevelItem(self._order_item(order, settings))
        self.tree.setSortingEnabled(True)

        n = len(orders)
        self.count_label.setText(f"{n} order{'' if n == 1 else 's'}")

    def _order_item(self, order, settings) -> _Item:
        rollup = calc.order_rollup(order, settings)
        total_weight = sum(p.weight_grams for p in order.plates)
        total_time = sum(p.print_time_minutes for p in order.plates)

        item = _Item()
        item.order = order
        item.plate = None
        item.setText(0, order.date_time.strftime("%d %b %Y"))
        item.setData(0, Qt.UserRole, order.date_time.timestamp())
        item.setToolTip(0, order.date_time.strftime("%d %b %Y  %H:%M")
                        + f"   ·   {PRICING_MODE_LABELS[order.pricing_mode]}")
        item.setText(1, order.customer_name or "—")
        item.setText(2, order.title or "—")
        self._set_numeric(item, 3, total_weight, fmt_grams(total_weight))
        self._set_numeric(item, 4, total_time, fmt_minutes(total_time))
        self._set_numeric(item, 5, rollup["total_cogs"], fmt_money(rollup["total_cogs"]))
        self._set_numeric(item, 6, rollup["final_price"], fmt_money(rollup["final_price"]))
        self._set_numeric(item, 7, rollup["profit"], fmt_money(rollup["profit"]),
                          tone_positive=rollup["profit"] >= 0)
        self._set_numeric(item, 8, rollup["margin_percent"],
                          f"{rollup['margin_percent']:.1f}%")

        font = item.font(0)
        font.setBold(True)
        for c in range(len(COLUMNS)):
            item.setFont(c, font)

        for plate in order.plates:
            item.addChild(self._plate_item(plate, order))
        return item

    def _plate_item(self, plate, order) -> _Item:
        child = _Item()
        child.order = order
        child.plate = plate
        label = plate.plate_label or "Plate"
        if plate.is_reprint:
            label = "↻ " + label
        child.setText(0, label)
        if plate.is_reprint and plate.linked_plate_id:
            child.setToolTip(0, f"Reprint of plate #{plate.linked_plate_id}")
        child.setText(1, plate.material_type)
        child.setText(2, MATERIAL_SOURCE_LABELS.get(plate.material_source,
                                                    plate.material_source))
        self._set_numeric(child, 3, plate.weight_grams, fmt_grams(plate.weight_grams))
        self._set_numeric(child, 4, plate.print_time_minutes,
                          fmt_minutes(plate.print_time_minutes))
        pcogs = calc.plate_cogs(plate)
        self._set_numeric(child, 5, pcogs, fmt_money(pcogs))
        if order.pricing_mode == "per_plate":
            self._set_numeric(child, 6, plate.final_price or 0,
                              fmt_money(plate.final_price))
            self._set_numeric(child, 7, plate.profit or 0,
                              fmt_money(plate.profit),
                              tone_positive=(plate.profit or 0) >= 0)
        else:
            child.setText(6, "")
            child.setText(7, "")
        child.setText(8, "")
        return child

    def _set_numeric(self, item, col, value, text, tone_positive=None) -> None:
        item.setText(col, text)
        item.setData(col, Qt.UserRole, float(value))
        item.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
        if tone_positive is not None:
            item.setForeground(col, QBrush(QColor(POSITIVE if tone_positive else NEGATIVE)))

    # -- actions ------------------------------------------------------------
    def _on_double_click(self, item, _column) -> None:
        order = getattr(item, "order", None)
        if order is not None:
            self.window.open_order_for_edit(order)

    def _context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        plate = getattr(item, "plate", None)
        order = getattr(item, "order", None)
        if plate is not None:
            menu.addAction("Log reprint…", lambda: self.window.log_reprint(plate))
            menu.addSeparator()
            menu.addAction("Edit order…", lambda: self.window.open_order_for_edit(order))
        elif order is not None:
            menu.addAction("Edit order…", lambda: self.window.open_order_for_edit(order))
            menu.addAction("Delete order…",
                           lambda: self.window.confirm_delete_order(order, self))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _export_csv(self) -> None:
        """Export the currently filtered orders, one row per plate."""
        orders = self.db.list_orders(**self._current_filters())
        if not orders:
            QMessageBox.information(self, "Export CSV",
                                    "No orders match the current filters.")
            return
        default_name = f"spoolbook-export-{datetime.now():%Y%m%d}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", default_name, "CSV files (*.csv)")
        if not path:
            return
        try:
            count = write_csv(orders, self.db.get_settings(), path)
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        QMessageBox.information(
            self, "Export complete",
            f"Wrote {count} plate row(s) from {len(orders)} order(s).")
