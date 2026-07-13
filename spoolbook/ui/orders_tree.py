"""Shared builders for the expandable order → plate tree.

History and Queue show the exact same rows (an order with its plates as
children); only the surrounding chrome and row actions differ. Keeping the row
construction here means the two screens stay visually identical and there is a
single place to change a column.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QTreeWidgetItem

from .. import calculations as calc
from ..config import MATERIAL_SOURCE_LABELS, PRICING_MODE_LABELS
from .theme import NEGATIVE, POSITIVE
from .widgets import fmt_grams, fmt_minutes, fmt_money

COLUMNS = ["Date · Plate", "Customer · Material", "Title · Source",
           "Weight", "Time", "COGS", "Price", "Profit", "Margin"]


class OrderItem(QTreeWidgetItem):
    """Tree item that sorts numeric columns by stored value, not text."""

    def __lt__(self, other: "OrderItem") -> bool:
        tree = self.treeWidget()
        col = tree.sortColumn() if tree else 0
        a = self.data(col, Qt.UserRole)
        b = other.data(col, Qt.UserRole)
        if a is not None and b is not None:
            return a < b
        return self.text(col) < other.text(col)


def set_numeric(item, col, value, text, tone_positive=None) -> None:
    item.setText(col, text)
    item.setData(col, Qt.UserRole, float(value))
    item.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
    if tone_positive is not None:
        item.setForeground(col, QBrush(QColor(POSITIVE if tone_positive else NEGATIVE)))


def build_order_item(order, settings) -> OrderItem:
    """A bold top-level row for an order, with its plates added as children."""
    rollup = calc.order_rollup(order, settings)
    total_weight = sum(p.weight_grams for p in order.plates)
    total_time = sum(p.print_time_minutes for p in order.plates)

    item = OrderItem()
    item.order = order
    item.plate = None
    item.setText(0, order.date_time.strftime("%d %b %Y"))
    item.setData(0, Qt.UserRole, order.date_time.timestamp())
    item.setToolTip(0, order.date_time.strftime("%d %b %Y  %H:%M")
                    + f"   ·   {PRICING_MODE_LABELS[order.pricing_mode]}")
    item.setText(1, order.customer_name or "—")
    item.setText(2, order.title or "—")
    set_numeric(item, 3, total_weight, fmt_grams(total_weight))
    set_numeric(item, 4, total_time, fmt_minutes(total_time))
    set_numeric(item, 5, rollup["cogs_per_unit_delivered"], fmt_money(rollup["cogs_per_unit_delivered"]))
    set_numeric(item, 6, rollup["final_price"], fmt_money(rollup["final_price"]))
    set_numeric(item, 7, rollup["profit"], fmt_money(rollup["profit"]),
                tone_positive=rollup["profit"] >= 0)
    set_numeric(item, 8, rollup["margin_percent"], f"{rollup['margin_percent']:.1f}%")

    font = item.font(0)
    font.setBold(True)
    for c in range(len(COLUMNS)):
        item.setFont(c, font)

    for plate in order.plates:
        item.addChild(build_plate_item(plate, order))
    return item


def build_plate_item(plate, order) -> OrderItem:
    child = OrderItem()
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
    set_numeric(child, 3, plate.weight_grams, fmt_grams(plate.weight_grams))
    set_numeric(child, 4, plate.print_time_minutes,
                fmt_minutes(plate.print_time_minutes))
    pcogs = calc.plate_cogs(plate)
    set_numeric(child, 5, pcogs, fmt_money(pcogs))
    if order.pricing_mode == "per_plate":
        set_numeric(child, 6, plate.final_price or 0, fmt_money(plate.final_price))
        set_numeric(child, 7, plate.profit or 0, fmt_money(plate.profit),
                    tone_positive=(plate.profit or 0) >= 0)
    else:
        child.setText(6, "")
        child.setText(7, "")
    child.setText(8, "")
    return child
