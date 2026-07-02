"""Small shared UI building blocks and value formatters.

Keeping these in one place makes every screen look consistent and gives the
stylesheet a stable set of object names to target.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import CURRENCY

# --- formatters ------------------------------------------------------------
def fmt_money(value, symbol: bool = True) -> str:
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    body = f"{abs(value):,.2f}"
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
