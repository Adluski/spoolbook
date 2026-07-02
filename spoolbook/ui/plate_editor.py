"""Reusable multi-plate editor: a header + a stack of editable plate rows.

Shared by the order screen and the scratch calculator. Adding/removing rows
is the everyday action here, so it is one click each. Each row owns a Plate
model instance and writes edits straight back into it; the editor emits
``changed`` so the parent can refresh live totals.

Rate snapshots: a fresh row captures the current settings rate for its
material. Changing a row's material re-captures the current rate (you are
re-costing that plate now). Editing weight/time never touches the snapshot,
and loading a saved plate keeps whatever rate it was stored with.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..calculations import plate_cogs, plate_machine_cost, plate_material_cost
from ..config import (
    MATERIAL_SOURCE_LABELS,
    MATERIAL_SOURCES,
    MATERIALS,
    machine_rate_key,
    material_rate_key,
)
from ..models import Plate
from .widgets import (
    DurationEditor,
    field_label,
    fmt_money,
    money_spin,
    plain_double_spin,
)

# Column widths shared by the header and every row so they line up as columns.
# Kept tight so per-plate mode (which adds Price + Profit) still fits without a
# horizontal scrollbar at the default window width.
W_MATERIAL = 74
W_SOURCE = 134
W_WEIGHT = 86
W_TIME = 116
W_COGS = 96
W_PRICE = 98
W_PROFIT = 98
W_REMOVE = 30
LABEL_MIN = 120
COL_SPACING = 6


def _fixed(widget: QWidget, width: int) -> QWidget:
    widget.setFixedWidth(width)
    return widget


class PlateRow(QFrame):
    changed = Signal()
    remove_requested = Signal(object)

    def __init__(self, plate: Plate, settings: dict, pricing_mode: str, index: int, parent=None):
        super().__init__(parent)
        self.setObjectName("PlateRow")
        self.plate = plate
        self.settings = settings
        self.pricing_mode = pricing_mode

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 6, 6)
        lay.setSpacing(COL_SPACING)

        # -- label cell (stretch) with reprint badge ------------------------
        label_cell = QWidget()
        lc = QHBoxLayout(label_cell)
        lc.setContentsMargins(0, 0, 0, 0)
        lc.setSpacing(6)
        self.badge = QLabel("↻")
        self.badge.setObjectName("ReprintBadge")
        self.badge.setToolTip("Reprint")
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText(f"Plate {index}")
        lc.addWidget(self.badge)
        lc.addWidget(self.label_edit, 1)
        label_cell.setMinimumWidth(LABEL_MIN)
        lay.addWidget(label_cell, 1)

        # -- material / source ---------------------------------------------
        self.material = QComboBox()
        for mt in MATERIALS:
            self.material.addItem(mt, mt)
        lay.addWidget(_fixed(self.material, W_MATERIAL))

        self.source = QComboBox()
        for src in MATERIAL_SOURCES:
            self.source.addItem(MATERIAL_SOURCE_LABELS[src], src)
        lay.addWidget(_fixed(self.source, W_SOURCE))

        # -- weight / time --------------------------------------------------
        self.weight = plain_double_spin(0, 100_000, decimals=2, step=1, suffix=" g")
        lay.addWidget(_fixed(self.weight, W_WEIGHT))

        self.duration = DurationEditor()
        lay.addWidget(_fixed(self.duration, W_TIME))

        # -- computed cogs --------------------------------------------------
        self.cogs = QLabel("—")
        self.cogs.setObjectName("RowCogs")
        self.cogs.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(_fixed(self.cogs, W_COGS))

        # -- per-plate price / profit --------------------------------------
        self.price = money_spin(maximum=10_000_000)
        self.profit = money_spin(minimum=-10_000_000, maximum=10_000_000)
        lay.addWidget(_fixed(self.price, W_PRICE))
        lay.addWidget(_fixed(self.profit, W_PROFIT))

        # -- remove ---------------------------------------------------------
        remove = QPushButton("✕")
        remove.setObjectName("RowRemove")
        remove.setCursor(Qt.PointingHandCursor)
        remove.setToolTip("Remove plate")
        remove.clicked.connect(lambda: self.remove_requested.emit(self))
        lay.addWidget(_fixed(remove, W_REMOVE))

        self._populate()
        self._connect()
        self.apply_pricing_mode(pricing_mode)

    # -- population ---------------------------------------------------------
    def _populate(self) -> None:
        for w in (self.label_edit, self.material, self.source,
                  self.weight, self.duration, self.price, self.profit):
            w.blockSignals(True)
        self.label_edit.setText(self.plate.plate_label)
        self.material.setCurrentIndex(max(0, self.material.findData(self.plate.material_type)))
        self.source.setCurrentIndex(max(0, self.source.findData(self.plate.material_source)))
        self.weight.setValue(self.plate.weight_grams)
        self.duration.set_minutes(self.plate.print_time_minutes)
        self.price.setValue(self.plate.final_price or 0.0)
        self.profit.setValue(self.plate.profit or 0.0)
        for w in (self.label_edit, self.material, self.source,
                  self.weight, self.duration, self.price, self.profit):
            w.blockSignals(False)
        self.badge.setVisible(self.plate.is_reprint)
        if self.plate.is_reprint and self.plate.linked_plate_id:
            self.badge.setToolTip(f"Reprint of plate #{self.plate.linked_plate_id}")
        self._refresh_cogs()

    def _connect(self) -> None:
        self.label_edit.textChanged.connect(self._commit)
        self.material.currentIndexChanged.connect(self._material_changed)
        self.source.currentIndexChanged.connect(self._commit)
        self.weight.valueChanged.connect(self._commit)
        self.duration.valueChanged.connect(self._commit)
        self.price.valueChanged.connect(self._commit)
        self.profit.valueChanged.connect(self._commit)

    # -- editing ------------------------------------------------------------
    def _material_changed(self) -> None:
        self._snapshot_rates()
        self._commit()

    def _snapshot_rates(self) -> None:
        mt = self.material.currentData()
        self.plate.material_rate_per_gram = self.settings[material_rate_key(mt)]
        self.plate.machine_rate_per_hour = self.settings[machine_rate_key(mt)]

    def _commit(self) -> None:
        p = self.plate
        p.plate_label = self.label_edit.text().strip()
        p.material_type = self.material.currentData()
        p.material_source = self.source.currentData()
        p.weight_grams = round(self.weight.value(), 2)
        p.print_time_minutes = self.duration.minutes()
        if self.pricing_mode == "per_plate":
            p.final_price = round(self.price.value(), 2)
            p.profit = round(self.profit.value(), 2)
        self._refresh_cogs()
        self.changed.emit()

    def _refresh_cogs(self) -> None:
        material = plate_material_cost(self.plate)
        machine = plate_machine_cost(self.plate)
        self.cogs.setText(fmt_money(material + machine))
        rate = self.plate.material_rate_per_gram
        mrate = self.plate.machine_rate_per_hour
        self.cogs.setToolTip(
            f"Material {fmt_money(material)}  (@ {fmt_money(rate)}/g)\n"
            f"Machine  {fmt_money(machine)}  (@ {fmt_money(mrate)}/h)"
        )

    def apply_pricing_mode(self, mode: str) -> None:
        self.pricing_mode = mode
        per_plate = mode == "per_plate"
        self.price.setVisible(per_plate)
        self.profit.setVisible(per_plate)
        if per_plate:
            # Pull the current spin values into the model.
            self.plate.final_price = round(self.price.value(), 2)
            self.plate.profit = round(self.profit.value(), 2)


class PlateRowsEditor(QWidget):
    """Header + list of PlateRow widgets + an add button."""

    changed = Signal()

    def __init__(self, settings: dict, pricing_mode: str = "order_level", parent=None):
        super().__init__(parent)
        self.settings = settings
        self.pricing_mode = pricing_mode
        self._rows: list[PlateRow] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header = self._build_header()
        outer.addWidget(self._header)

        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)
        outer.addWidget(self._rows_host)

        add_bar = QWidget()
        ab = QHBoxLayout(add_bar)
        ab.setContentsMargins(10, 8, 8, 4)
        add_btn = QPushButton("+  Add plate")
        add_btn.setObjectName("AddPlateButton")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(lambda: self.add_plate())
        ab.addWidget(add_btn)
        ab.addStretch(1)
        self._empty_hint = QLabel("No plates yet — add one to start costing.")
        self._empty_hint.setObjectName("Muted")
        ab.addWidget(self._empty_hint)
        outer.addWidget(add_bar)

        self._apply_mode_to_header()

    # -- header -------------------------------------------------------------
    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("PlateHeader")
        lay = QHBoxLayout(header)
        lay.setContentsMargins(10, 7, 6, 7)
        lay.setSpacing(COL_SPACING)

        def col(text, width=None, align=Qt.AlignLeft):
            lbl = QLabel(text.upper())
            lbl.setObjectName("ColHead")
            lbl.setAlignment(align | Qt.AlignVCenter)
            if width:
                lbl.setFixedWidth(width)
            return lbl

        lay.addWidget(col("Plate label"), 1)
        lay.addWidget(col("Material", W_MATERIAL))
        lay.addWidget(col("Source", W_SOURCE))
        lay.addWidget(col("Weight", W_WEIGHT, Qt.AlignRight))
        lay.addWidget(col("Print time", W_TIME))
        lay.addWidget(col("COGS", W_COGS, Qt.AlignRight))
        self._h_price = col("Price", W_PRICE, Qt.AlignRight)
        self._h_profit = col("Profit", W_PROFIT, Qt.AlignRight)
        lay.addWidget(self._h_price)
        lay.addWidget(self._h_profit)
        lay.addWidget(col("", W_REMOVE))
        return header

    def _apply_mode_to_header(self) -> None:
        per_plate = self.pricing_mode == "per_plate"
        self._h_price.setVisible(per_plate)
        self._h_profit.setVisible(per_plate)

    # -- settings / mode ----------------------------------------------------
    def set_settings(self, settings: dict) -> None:
        self.settings = settings
        for row in self._rows:
            row.settings = settings

    def set_pricing_mode(self, mode: str) -> None:
        self.pricing_mode = mode
        self._apply_mode_to_header()
        for row in self._rows:
            row.apply_pricing_mode(mode)
        self.changed.emit()

    # -- rows ---------------------------------------------------------------
    def _snapshot_new(self, plate: Plate) -> None:
        mt = plate.material_type
        plate.material_rate_per_gram = self.settings[material_rate_key(mt)]
        plate.machine_rate_per_hour = self.settings[machine_rate_key(mt)]

    def add_plate(self, plate: Plate | None = None) -> PlateRow:
        if plate is None:
            plate = Plate()
            self._snapshot_new(plate)
        row = PlateRow(plate, self.settings, self.pricing_mode, len(self._rows) + 1)
        row.changed.connect(self.changed)
        row.remove_requested.connect(self._remove_row)
        self._rows.append(row)
        self._rows_layout.addWidget(row)
        self._update_empty_hint()
        self.changed.emit()
        return row

    def _remove_row(self, row: PlateRow) -> None:
        if row in self._rows:
            self._rows.remove(row)
            self._rows_layout.removeWidget(row)
            row.deleteLater()
            self._update_empty_hint()
            self.changed.emit()

    def set_plates(self, plates: list[Plate]) -> None:
        self.clear()
        for plate in plates:
            self.add_plate(plate)
        if not plates:
            self._update_empty_hint()

    def clear(self) -> None:
        for row in list(self._rows):
            self._rows.remove(row)
            self._rows_layout.removeWidget(row)
            row.deleteLater()
        self._update_empty_hint()

    def plates(self) -> list[Plate]:
        return [row.plate for row in self._rows]

    def _update_empty_hint(self) -> None:
        self._empty_hint.setVisible(not self._rows)
