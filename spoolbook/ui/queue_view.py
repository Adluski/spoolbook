"""Queue: planned prints (status = "queued") that haven't been run yet.

Structurally the same expandable order → plate tree as History, but scoped to
queued orders. The price and profit shown here are *planned* figures: queued
orders are excluded from the dashboard until they are marked complete (which
also captures the actual weight / time / price).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from .mark_complete_dialog import MarkCompleteDialog
from .orders_tree import build_order_item
from .widgets import PageHeader

QUEUE_COLUMNS = ["Date · Plate", "Customer · Material", "Title · Source",
                 "Weight", "Time", "COGS", "Planned price", "Planned profit",
                 "Margin"]


class QueueView(QWidget):
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
        tl.addWidget(PageHeader(
            "Queue", "Planned prints — not counted in the dashboard until complete."))
        tl.addStretch(1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        tl.addWidget(self.count_label)
        outer.addWidget(top)

        outer.addWidget(self._build_tree(), 1)
        self.refresh()

    def _build_tree(self) -> QWidget:
        self.tree = QTreeWidget()
        self.tree.setObjectName("HistoryTree")
        self.tree.setColumnCount(len(QUEUE_COLUMNS))
        self.tree.setHeaderLabels(QUEUE_COLUMNS)
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
        for c in range(3, len(QUEUE_COLUMNS)):
            header.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.tree.setColumnWidth(1, 150)

        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(32, 12, 32, 20)
        wl.addWidget(self.tree)
        return wrap

    # -- population ---------------------------------------------------------
    def refresh(self) -> None:
        settings = self.db.get_settings()
        orders = self.db.list_orders(status="queued")

        self.tree.setSortingEnabled(False)
        self.tree.clear()
        # build_order_item lays out the same 9 columns History uses; ours only
        # relabels columns 6/7 as "planned".
        for order in orders:
            self.tree.addTopLevelItem(build_order_item(order, settings))
        self.tree.setSortingEnabled(True)

        n = len(orders)
        self.count_label.setText(f"{n} queued")

    # -- actions ------------------------------------------------------------
    def _on_double_click(self, item, _column) -> None:
        # Match History: double-click edits. Mark-complete is the first
        # context-menu action (and needs the dialog anyway).
        order = getattr(item, "order", None)
        if order is not None:
            self.window.open_order_for_edit(order)

    def _context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return
        order = getattr(item, "order", None)
        if order is None:
            return
        menu = QMenu(self)
        menu.addAction("Mark complete…", lambda: self._mark_complete(order))
        menu.addAction("Edit order…", lambda: self.window.open_order_for_edit(order))
        menu.addSeparator()
        menu.addAction("Delete order…",
                       lambda: self.window.confirm_delete_order(order, self))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _mark_complete(self, order) -> None:
        dialog = MarkCompleteDialog(order, self.db.get_settings(), self)
        if dialog.exec() == QDialog.Accepted:
            self.db.save_order(order)          # persists status + any edited actuals
            self.window._refresh_data_views()  # drop it from the Queue, add to History
