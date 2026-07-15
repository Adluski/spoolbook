"""Log failed print attempts for a single plate.

Operates on a deep copy of the plate's failed_attempts list — the caller's
plate is only touched if the dialog is accepted (`self.plate.failed_attempts`
is overwritten in `_on_accept`), so Cancel discards cleanly with nothing
written back mid-edit. Costs are always computed by calling into
calculations.py; no arithmetic happens here.
"""
from __future__ import annotations

import copy
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import calculations as calc
from ..models import FailedAttempt, Plate
from .frameless import FramelessDialog
from .widgets import field_label, fmt_money, int_spin, section_label


class FailedAttemptsDialog(FramelessDialog):
    def __init__(self, plate: Plate, index: int, parent=None):
        plate_name = plate.plate_label or f"Plate {index}"
        title_text = f"Failed attempts — {plate_name}"
        super().__init__(title=title_text, parent=parent)
        self.plate = plate
        self._attempts = copy.deepcopy(plate.failed_attempts)
        self._rows: list[dict] = []
        self.setMinimumWidth(420)

        outer = QVBoxLayout(self.body)
        outer.setContentsMargins(22, 20, 22, 18)
        outer.setSpacing(14)

        head = QLabel(f"<b>{title_text}</b>")
        head.setObjectName("DialogNote")
        outer.addWidget(head)

        outer.addWidget(section_label("Attempts"))
        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)
        outer.addWidget(self._rows_host)

        for attempt in self._attempts:
            self._add_row(attempt)

        add_btn = QPushButton("+  Add attempt")
        add_btn.setObjectName("AddPlateButton")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._add_attempt)
        outer.addWidget(add_btn)

        self.summary = QLabel("")
        self.summary.setObjectName("FormulaHint")
        outer.addWidget(self.summary)

        buttons = QDialogButtonBox()
        ok = buttons.addButton("OK", QDialogButtonBox.AcceptRole)
        ok.setObjectName("PrimaryButton")
        cancel = buttons.addButton(QDialogButtonBox.Cancel)
        cancel.setObjectName("SecondaryButton")
        ok.clicked.connect(self._on_accept)
        cancel.clicked.connect(self.reject)
        outer.addWidget(buttons)

        self._recompute()

    # -- rows -----------------------------------------------------------
    def _add_row(self, attempt: FailedAttempt) -> None:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        label = field_label("")
        spin = int_spin(1, 100, suffix=" %")
        spin.setValue(max(1, min(100, int(round(attempt.completion_percent or 50)))))
        spin.setFixedWidth(90)
        remove = QPushButton("✕")
        remove.setObjectName("RowRemove")
        remove.setCursor(Qt.PointingHandCursor)
        remove.setToolTip("Remove attempt")
        lay.addWidget(label)
        lay.addWidget(spin, 1)
        lay.addWidget(remove)
        self._rows_layout.addWidget(row)

        entry = {"container": row, "attempt": attempt, "spin": spin, "label": label}
        spin.valueChanged.connect(lambda v, a=attempt: self._on_spin_changed(a, v))
        remove.clicked.connect(lambda: self._remove_row(entry))
        self._rows.append(entry)
        self._renumber()

    def _renumber(self) -> None:
        for i, entry in enumerate(self._rows, start=1):
            entry["label"].setText(f"Attempt {i}")

    def _add_attempt(self) -> None:
        attempt = FailedAttempt(completion_percent=50.0, position=len(self._attempts))
        self._attempts.append(attempt)
        self._add_row(attempt)
        self._recompute()

    def _remove_row(self, entry: dict) -> None:
        self._rows.remove(entry)
        self._attempts.remove(entry["attempt"])
        self._rows_layout.removeWidget(entry["container"])
        entry["container"].deleteLater()
        self._renumber()
        self._recompute()

    def _on_spin_changed(self, attempt: FailedAttempt, value: int) -> None:
        attempt.completion_percent = float(value)
        self._recompute()

    # -- live footer ------------------------------------------------------
    def _recompute(self) -> None:
        temp = replace(self.plate, failed_attempts=self._attempts)
        material = calc.plate_failed_material_cost(temp)
        machine = calc.plate_failed_machine_cost(temp)
        total = calc.plate_failed_cost(temp)
        self.summary.setText(
            f"Wasted: material {fmt_money(material)} · machine {fmt_money(machine)} "
            f"· total {fmt_money(total)}")

    # -- accept / cancel ---------------------------------------------------
    def _on_accept(self) -> None:
        for i, attempt in enumerate(self._attempts):
            attempt.position = i
        self.plate.failed_attempts = self._attempts
        self.accept()
