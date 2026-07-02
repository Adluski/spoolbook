"""Small shared UI building blocks and value formatters.

Keeping these in one place makes every screen look consistent and gives the
stylesheet a stable set of object names to target.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QButtonGroup,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import CURRENCY

# --- formatters ------------------------------------------------------------
def fmt_money(value, symbol: bool = True) -> str:
    if value is None:
        return "—"
    # Round half-up so displayed money matches calculations.round_money.
    cents = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if cents < 0 else ""
    body = f"{abs(cents):,.2f}"
    return f"{sign}{CURRENCY}{body}" if symbol else f"{sign}{body}"


def fmt_grams(grams) -> str:
    if grams is None:
        return "—"
    return f"{grams:,.2f} g"


def fmt_minutes(minutes) -> str:
    if minutes is None:
        return "—"
    minutes = int(round(minutes))
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours}h {mins:02d}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


def fmt_percent(value) -> str:
    return "—" if value is None else f"{value:.1f}%"


# --- widgets ---------------------------------------------------------------
class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("PageTitle")
        lay.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("PageSubtitle")
            s.setWordWrap(True)
            lay.addWidget(s)


class Panel(QFrame):
    """A flat, hairline-bordered content surface."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")


def section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setObjectName("SectionLabel")
    return lbl


def hline() -> QFrame:
    line = QFrame()
    line.setObjectName("HLine")
    line.setFrameShape(QFrame.HLine)
    line.setFixedHeight(1)
    return line


def field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("FieldLabel")
    return lbl


def money_spin(minimum: float = 0.0, maximum: float = 10_000_000.0,
               decimals: int = 2, prefix: str = CURRENCY,
               step: float = 1.0) -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(minimum, maximum)
    sb.setDecimals(decimals)
    if prefix:
        sb.setPrefix(prefix)
    sb.setSingleStep(step)
    sb.setGroupSeparatorShown(True)
    sb.setButtonSymbols(QAbstractSpinBox.NoButtons)
    sb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return sb


def plain_double_spin(minimum: float, maximum: float, decimals: int,
                      step: float = 1.0, suffix: str = "") -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(minimum, maximum)
    sb.setDecimals(decimals)
    sb.setSingleStep(step)
    if suffix:
        sb.setSuffix(suffix)
    sb.setButtonSymbols(QAbstractSpinBox.NoButtons)
    sb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return sb


def int_spin(minimum: int = 0, maximum: int = 1_000_000, suffix: str = "") -> QSpinBox:
    sb = QSpinBox()
    sb.setRange(minimum, maximum)
    if suffix:
        sb.setSuffix(suffix)
    sb.setButtonSymbols(QAbstractSpinBox.NoButtons)
    sb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return sb


class DurationEditor(QWidget):
    """Enter a print time as hours + minutes; value is total minutes."""

    valueChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self._hours = int_spin(0, 999)
        self._hours.setFixedWidth(46)
        self._mins = int_spin(0, 59)
        self._mins.setFixedWidth(42)
        h_lbl = QLabel("h")
        h_lbl.setObjectName("UnitLabel")
        m_lbl = QLabel("m")
        m_lbl.setObjectName("UnitLabel")
        lay.addWidget(self._hours)
        lay.addWidget(h_lbl)
        lay.addWidget(self._mins)
        lay.addWidget(m_lbl)
        self._hours.valueChanged.connect(self.valueChanged)
        self._mins.valueChanged.connect(self.valueChanged)

    def minutes(self) -> int:
        return self._hours.value() * 60 + self._mins.value()

    def set_minutes(self, total) -> None:
        total = int(round(total or 0))
        self._hours.blockSignals(True)
        self._mins.blockSignals(True)
        self._hours.setValue(total // 60)
        self._mins.setValue(total % 60)
        self._hours.blockSignals(False)
        self._mins.blockSignals(False)


class StatChip(QFrame):
    """A read-only caption + value block for summary bars (no drop shadow)."""

    def __init__(self, caption: str, value: str = "—",
                 value_name: str = "StatValue", parent=None):
        super().__init__(parent)
        self.setObjectName("StatChip")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(1)
        cap = QLabel(caption.upper())
        cap.setObjectName("StatCaption")
        self._value = QLabel(value)
        self._value.setObjectName(value_name)
        lay.addWidget(cap)
        lay.addWidget(self._value)

    def set_value(self, text: str, tone: str | None = None) -> None:
        self._value.setText(text)
        self._value.setProperty("tone", tone or "")
        self._value.style().unpolish(self._value)
        self._value.style().polish(self._value)


class SegmentedToggle(QWidget):
    """A compact 2+ segment single-choice control (used for pricing mode)."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for key, label in options:
            btn = QPushButton(label)
            btn.setObjectName("SegItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._on_click(k))
            self._group.addButton(btn)
            self._buttons[key] = btn
            lay.addWidget(btn)
        if options:
            self._buttons[options[0][0]].setChecked(True)

    def _on_click(self, key: str) -> None:
        self.changed.emit(key)

    def value(self) -> str:
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return ""

    def set_value(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn and not btn.isChecked():
            btn.setChecked(True)


def row(*widgets, spacing: int = 8, margins=(0, 0, 0, 0)) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for item in widgets:
        if item == "stretch":
            lay.addStretch(1)
        elif isinstance(item, QWidget):
            lay.addWidget(item)
    return w
