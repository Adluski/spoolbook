"""History: every saved order as an expandable row over its plates.

Filterable by customer, date range, material and reprint status; sortable by
any column (numeric columns sort numerically). Right-click an order to edit or
delete it, or a plate to log a reprint.
"""
from __future__ import annotations

from datetime import datetime, time

from PySide6.QtCore import QDate, Qt
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
    QVBoxLayout,
    QWidget,
)

from ..csv_export import write_csv
from ..config import MATERIALS
from .cost_breakdown_dialog import CostBreakdownDialog
from .orders_tree import COLUMNS, build_order_item
from .widgets import PageHeader


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
        self.delete_btn = QPushButton("Delete order")
        self.delete_btn.setObjectName("DangerButton")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setEnabled(False)
        self.delete_btn.setToolTip("Select an order (or one of its plates) to delete it.")
        self.delete_btn.clicked.connect(self._delete_selected)
        tl.addWidget(self.delete_btn)
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
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)

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
        # History is realized orders only; planned prints live in the Queue.
        filters: dict = {"status": "completed"}
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
            self.tree.addTopLevelItem(build_order_item(order, settings))
        self.tree.setSortingEnabled(True)

        n = len(orders)
        self.count_label.setText(f"{n} order{'' if n == 1 else 's'}")
        self._on_selection_changed()

    # -- actions ------------------------------------------------------------
    def _selected_order(self):
        """The order behind the current row, whether it's an order row or one
        of its plate children — both carry an `order` attribute."""
        item = self.tree.currentItem()
        return getattr(item, "order", None) if item is not None else None

    def _on_selection_changed(self) -> None:
        self.delete_btn.setEnabled(self._selected_order() is not None)

    def _delete_selected(self) -> None:
        order = self._selected_order()
        if order is None:
            return
        self.window.confirm_delete_order(order, self)

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
        # Always the last item, in both views, whatever the row: inspect the
        # full costing without opening an editor that could re-save it.
        if order is not None:
            menu.addSeparator()
            menu.addAction("Cost breakdown…", lambda: self._show_breakdown(order))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _show_breakdown(self, order) -> None:
        CostBreakdownDialog(order, self.db.get_settings(), self).exec()

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
