"""Log a reprint of an existing plate.

Creates a NEW plate on the same order (is_reprint=True, linked to the
original) capturing just the extra weight/time — no need to re-enter any order
details. Rates snapshot at current settings, since the reprint is happening
now.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from ..config import (
    MATERIAL_SOURCE_LABELS,
    MATERIAL_SOURCES,
    MATERIALS,
    machine_rate_key,
    material_rate_key,
)
from ..models import Plate
from .frameless import FramelessDialog
from .widgets import (
    DurationEditor,
    field_label,
    fmt_grams,
    fmt_minutes,
    fmt_money,
    plain_double_spin,
)


class ReprintDialog(FramelessDialog):
    def __init__(self, source: Plate, settings: dict, parent=None):
        super().__init__(title="Log reprint", parent=parent)
        self.source = source
        self.settings = settings
        self.result_plate: Plate | None = None
        self.setMinimumWidth(420)

        outer = QVBoxLayout(self.body)
        outer.setContentsMargins(22, 20, 22, 18)
        outer.setSpacing(14)

        origin = QLabel(
            f"Reprinting <b>{source.plate_label or 'plate'}</b>"
            f" — original {fmt_grams(source.weight_grams)},"
            f" {fmt_minutes(source.print_time_minutes)}."
        )
        origin.setWordWrap(True)
        origin.setObjectName("DialogNote")
        outer.addWidget(origin)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)

        self.label_edit = QLineEdit()
        self.label_edit.setText(
            f"{source.plate_label} (reprint)" if source.plate_label else "Reprint")

        self.material = QComboBox()
        for mt in MATERIALS:
            self.material.addItem(mt, mt)
        self.material.setCurrentIndex(max(0, self.material.findData(source.material_type)))
        self.material.currentIndexChanged.connect(self._update_rate_note)

        self.source_combo = QComboBox()
        for src in MATERIAL_SOURCES:
            self.source_combo.addItem(MATERIAL_SOURCE_LABELS[src], src)
        self.source_combo.setCurrentIndex(
            max(0, self.source_combo.findData(source.material_source)))
        self.source_combo.currentIndexChanged.connect(self._update_rate_note)

        self.weight = plain_double_spin(0, 100_000, decimals=2, step=1, suffix=" g")
        self.duration = DurationEditor()

        form.addRow(field_label("Label"), self.label_edit)
        form.addRow(field_label("Material"), self.material)
        form.addRow(field_label("Source"), self.source_combo)
        form.addRow(field_label("Added weight"), self.weight)
        form.addRow(field_label("Added time"), self.duration)
        outer.addLayout(form)

        self.rate_note = QLabel("")
        self.rate_note.setObjectName("FormulaHint")
        outer.addWidget(self.rate_note)

        self.error = QLabel("")
        self.error.setObjectName("StatusError")
        outer.addWidget(self.error)

        buttons = QDialogButtonBox()
        self.ok_btn = buttons.addButton("Log reprint", QDialogButtonBox.AcceptRole)
        self.ok_btn.setObjectName("PrimaryButton")
        cancel = buttons.addButton(QDialogButtonBox.Cancel)
        cancel.setObjectName("SecondaryButton")
        self.ok_btn.clicked.connect(self._on_accept)
        cancel.clicked.connect(self.reject)
        outer.addWidget(buttons)

        self._update_rate_note()

    def _rates(self) -> tuple[float, float]:
        mt = self.material.currentData()
        return (self.settings[material_rate_key(mt)],
                self.settings[machine_rate_key(mt)])

    def _update_rate_note(self) -> None:
        mat_rate, mac_rate = self._rates()
        if self.source_combo.currentData() == "customer":
            self.rate_note.setText(
                f"Customer-supplied — no material cost. Machine @ {fmt_money(mac_rate)}/h.")
        else:
            self.rate_note.setText(
                f"Snapshots current rates: {fmt_money(mat_rate)}/g material,"
                f" {fmt_money(mac_rate)}/h machine.")

    def build_plate(self) -> Plate | None:
        """Validate and return the new reprint plate, or None if invalid."""
        weight = round(self.weight.value(), 2)
        minutes = self.duration.minutes()
        if weight <= 0 and minutes <= 0:
            self.error.setText("Enter the added weight and/or time for the reprint.")
            return None
        mat_rate, mac_rate = self._rates()
        return Plate(
            order_id=self.source.order_id,
            plate_label=self.label_edit.text().strip(),
            weight_grams=weight,
            print_time_minutes=minutes,
            material_type=self.material.currentData(),
            material_source=self.source_combo.currentData(),
            material_rate_per_gram=mat_rate,
            machine_rate_per_hour=mac_rate,
            is_reprint=True,
            linked_plate_id=self.source.id,
        )

    def _on_accept(self) -> None:
        plate = self.build_plate()
        if plate is not None:
            self.result_plate = plate
            self.accept()
