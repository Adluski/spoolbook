"""Scratch calculator: cost a job live without saving anything.

Reuses the same plate editor as the order screen. No customer, no title, no
database writes — just running totals and a suggested price. "Convert to
order" hands clean copies of the plates to the order screen to finalise.
State is never persisted; a fresh session starts with one empty plate.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import calculations as calc
from .plate_editor import PlateRowsEditor
from .widgets import PageHeader, Panel, StatChip, fmt_money, hline, section_label


class CalculatorView(QWidget):
    convert_requested = Signal(list)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.settings = db.get_settings()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = QFrame()
        top.setObjectName("TopBar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(32, 20, 32, 16)
        tl.addWidget(PageHeader(
            "Scratch calculator",
            "Nothing here is saved. Cost a job, then convert it to a real order.",
        ))
        tl.addStretch(1)
        clear = QPushButton("Clear")
        clear.setObjectName("SecondaryButton")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(self.clear)
        tl.addWidget(clear)
        outer.addWidget(top)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(32, 12, 32, 20)
        bl.setSpacing(18)

        panel = Panel()
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        head = QHBoxLayout()
        head.setContentsMargins(22, 16, 22, 10)
        head.addWidget(section_label("Plates"))
        head.addStretch(1)
        pl.addLayout(head)
        pl.addWidget(hline())
        self.plate_editor = PlateRowsEditor(self.settings, "order_level")
        pl.addWidget(self.plate_editor)
        bl.addWidget(panel)
        bl.addStretch(1)

        outer.addWidget(body, 1)
        outer.addWidget(self._build_totals())

        self.plate_editor.changed.connect(self._recompute)
        self.clear()

    def _build_totals(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("SummaryBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(32, 12, 32, 12)
        lay.setSpacing(10)
        self.chip_material = StatChip("Material")
        self.chip_machine = StatChip("Machine")
        self.chip_cogs = StatChip("Total COGS")
        self.chip_suggested = StatChip("Suggested price", value_name="StatValueStrong")
        for chip in (self.chip_material, self.chip_machine,
                     self.chip_cogs, self.chip_suggested):
            lay.addWidget(chip)
        lay.addStretch(1)
        convert = QPushButton("Convert to order  →")
        convert.setObjectName("PrimaryButton")
        convert.setCursor(Qt.PointingHandCursor)
        convert.clicked.connect(self._convert)
        lay.addWidget(convert)
        return bar

    def _recompute(self) -> None:
        plates = self.plate_editor.plates()
        markup = self.settings["markup_multiplier"]
        buffer = self.settings["pellet_buffer_percent"]
        material = calc.total_material_cost(plates)
        machine = calc.total_machine_cost(plates)
        self.chip_material.set_value(fmt_money(material))
        self.chip_machine.set_value(fmt_money(machine))
        self.chip_cogs.set_value(fmt_money(material + machine))
        self.chip_suggested.set_value(
            fmt_money(calc.suggested_unit_price(plates, markup, buffer)),
            tone="accent",
        )

    def clear(self) -> None:
        self.settings = self.db.get_settings()
        self.plate_editor.set_settings(self.settings)
        self.plate_editor.set_plates([])
        self.plate_editor.add_plate()
        self._recompute()

    def _convert(self) -> None:
        plates = [p.clone_for_calculator() for p in self.plate_editor.plates()]
        self.convert_requested.emit(plates)

    def on_settings_changed(self) -> None:
        self.settings = self.db.get_settings()
        self.plate_editor.set_settings(self.settings)
        self._recompute()
