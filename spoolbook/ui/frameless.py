"""Shared frameless chrome for modal dialogs.

The native OS title bar doesn't share the app's palette (a plain grey
Windows caption bar sitting above themed content). FramelessDialog replaces
it with a themed title strip using the same visual language as the app's
#TopBar, and stays fixed-size / close-button-only — no native resize or
maximize, since there is no native frame to provide them.

No drop shadow: restoring the one Windows normally draws around a window
would require DWM API calls via ctypes, which is out of scope here. These
dialogs render slightly flatter against the desktop than a native window
would.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _TitleBar(QWidget):
    """The draggable strip: title label + close button.

    Drag state is tracked only here, scoped to this widget, so a press
    that starts elsewhere (the dialog body) never begins a drag.
    """

    def __init__(self, dialog: "FramelessDialog", title: str):
        super().__init__(dialog)
        self.setObjectName("DialogTitleBar")
        self.setFixedHeight(38)
        self._dialog = dialog
        self._dragging = False
        self._drag_anchor = QPoint()

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 6, 0)
        lay.setSpacing(8)

        label = QLabel(title)
        label.setObjectName("DialogTitleLabel")
        lay.addWidget(label)
        lay.addStretch(1)

        close = QPushButton("×")
        close.setObjectName("DialogCloseButton")
        close.setFixedSize(26, 24)
        close.setCursor(Qt.PointingHandCursor)
        close.setToolTip("Close")
        close.clicked.connect(dialog.reject)
        lay.addWidget(close)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_anchor = (
                event.globalPosition().toPoint() - self._dialog.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and (event.buttons() & Qt.LeftButton):
            self._dialog.move(event.globalPosition().toPoint() - self._drag_anchor)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


class FramelessDialog(QDialog):
    """QDialog with a custom themed title bar instead of native OS chrome.

    Subclasses build their content into `self.body` (a plain QWidget)
    exactly as they previously built it into `self` — give it its own
    QVBoxLayout/QGridLayout/etc. as before.
    """

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setWindowTitle(title)  # taskbar / alt-tab label; no native bar shows it

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(_TitleBar(self, title))

        self.body = QWidget()
        outer.addWidget(self.body)
