"""Settings screen: edit the rates/multipliers that cost NEW plates.

Editing here never rewrites history — every existing plate keeps the rate
snapshot it was saved with. The screen makes that promise explicit.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import DEFAULT_SETTINGS
from .widgets import (
    PageHeader,
    Panel,
    field_label,
    hline,
    money_spin,
    plain_double_spin,
    section_label,
)


class SettingsView(QWidget):
    settings_saved = Signal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self._spins: dict[str, object] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 28)
        outer.setSpacing(18)

        outer.addWidget(PageHeader(
            "Settings",
            "Rates and multipliers used to cost new plates and suggest prices.",
        ))

        notice = QLabel(
            "Applies to new entries only.  Existing plates keep the exact rate "
            "they were saved with — nothing here changes historical costs."
        )
        notice.setObjectName("Notice")
        notice.setWordWrap(True)
        outer.addWidget(notice)

        outer.addWidget(self._build_form())

        outer.addWidget(self._build_actions())
        outer.addStretch(1)

        self.reload()

    # -- form ---------------------------------------------------------------
    def _build_form(self) -> Panel:
        panel = Panel()
        grid = QGridLayout(panel)
        grid.setContentsMargins(22, 20, 22, 20)
        grid.setHorizontalSpacing(40)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        # left column: material + machine rates ; right column: pricing
        grid.addWidget(section_label("Material rate — per gram"), 0, 0)
        mat = QFormLayout()
        mat.setHorizontalSpacing(16)
        mat.setVerticalSpacing(8)
        self._spins["pla_rate_per_gram"] = money_spin(decimals=2, step=0.05, maximum=10_000)
        self._spins["petg_rate_per_gram"] = money_spin(decimals=2, step=0.05, maximum=10_000)
        mat.addRow(field_label("PLA"), self._spins["pla_rate_per_gram"])
        mat.addRow(field_label("PETG"), self._spins["petg_rate_per_gram"])
        grid.addLayout(mat, 1, 0)

        grid.addWidget(section_label("Machine rate — per hour"), 2, 0)
        mac = QFormLayout()
        mac.setHorizontalSpacing(16)
        mac.setVerticalSpacing(8)
        self._spins["pla_machine_rate_per_hour"] = money_spin(decimals=2, step=1, maximum=100_000)
        self._spins["petg_machine_rate_per_hour"] = money_spin(decimals=2, step=1, maximum=100_000)
        mac.addRow(field_label("PLA"), self._spins["pla_machine_rate_per_hour"])
        mac.addRow(field_label("PETG"), self._spins["petg_machine_rate_per_hour"])
        grid.addLayout(mac, 3, 0)

        grid.addWidget(section_label("Pricing"), 0, 1)
        price = QFormLayout()
        price.setHorizontalSpacing(16)
        price.setVerticalSpacing(8)
        self._spins["markup_multiplier"] = plain_double_spin(
            0.5, 100.0, decimals=2, step=0.05, suffix=" ×")
        self._spins["pellet_buffer_percent"] = plain_double_spin(
            0.0, 100.0, decimals=1, step=0.5, suffix=" %")
        price.addRow(field_label("Markup multiplier"), self._spins["markup_multiplier"])
        price.addRow(field_label("Material buffer"), self._spins["pellet_buffer_percent"])
        grid.addLayout(price, 1, 1)

        hint = QLabel(
            "Suggested price = (COGS + buffer% × material cost) × markup"
        )
        hint.setObjectName("FormulaHint")
        hint.setWordWrap(True)
        grid.addWidget(hint, 3, 1, Qt.AlignBottom)

        return panel

    # -- actions ------------------------------------------------------------
    def _build_actions(self) -> QWidget:
        bar = QWidget()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        restore = QPushButton("Restore defaults")
        restore.setObjectName("SecondaryButton")
        restore.setCursor(Qt.PointingHandCursor)
        restore.clicked.connect(self._restore_defaults)
        lay.addWidget(restore)

        self.status = QLabel("")
        self.status.setObjectName("StatusOk")
        lay.addWidget(self.status)

        lay.addStretch(1)

        save = QPushButton("Save as new default")
        save.setObjectName("PrimaryButton")
        save.setCursor(Qt.PointingHandCursor)
        save.clicked.connect(self._save)
        lay.addWidget(save)
        return bar

    # -- data ---------------------------------------------------------------
    def reload(self) -> None:
        settings = self.db.get_settings()
        for key, spin in self._spins.items():
            spin.setValue(settings.get(key, DEFAULT_SETTINGS[key]))
        self.status.setText("")

    def _gather(self) -> dict[str, float]:
        return {key: float(spin.value()) for key, spin in self._spins.items()}

    def _save(self) -> None:
        self.db.update_settings(self._gather())
        self.status.setText("Saved — applies to new entries")
        self.settings_saved.emit()

    def _restore_defaults(self) -> None:
        for key, spin in self._spins.items():
            spin.setValue(DEFAULT_SETTINGS[key])
        self.status.setText("Defaults loaded — not saved yet")
