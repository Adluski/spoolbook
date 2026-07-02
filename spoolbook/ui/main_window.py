"""Main application window: a left rail of sections + a stacked content area.

A vertical nav rail (rather than a top QTabBar) keeps the app feeling like a
purpose-built tool and gives each screen the full width for dense tables.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..config import APP_NAME, APP_TAGLINE

# (key, label) for each rail entry, in display order.
SECTIONS = [
    ("calculator", "Calculator"),
    ("new_order", "New order"),
    ("history", "History"),
    ("dashboard", "Dashboard"),
    ("settings", "Settings"),
]


class MainWindow(QWidget):
    def __init__(self, db=None):
        super().__init__()
        self.db = db
        self.setWindowTitle(APP_NAME)
        self.resize(1180, 760)
        self.setMinimumSize(940, 600)

        self._pages: dict[str, QWidget] = {}
        self._nav_buttons: dict[str, QPushButton] = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_rail())

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self._build_pages()
        self._install_real_views()
        self.go_to("calculator")

    # -- navigation rail ----------------------------------------------------
    def _build_rail(self) -> QWidget:
        rail = QFrame()
        rail.setObjectName("NavRail")
        rail.setFixedWidth(196)
        rail.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        lay = QVBoxLayout(rail)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QWidget()
        header.setObjectName("NavHeader")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(18, 20, 16, 18)
        hl.setSpacing(2)
        wordmark = QLabel(APP_NAME)
        wordmark.setObjectName("Wordmark")
        tag = QLabel(APP_TAGLINE)
        tag.setObjectName("Tagline")
        tag.setWordWrap(True)
        hl.addWidget(wordmark)
        hl.addWidget(tag)
        lay.addWidget(header)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for key, label in SECTIONS:
            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._on_nav(k))
            self._nav_group.addButton(btn)
            self._nav_buttons[key] = btn
            lay.addWidget(btn)

        lay.addStretch(1)

        ver = QLabel(f"v{__version__}")
        ver.setObjectName("Version")
        ver.setContentsMargins(18, 0, 0, 14)
        lay.addWidget(ver)
        return rail

    # -- pages --------------------------------------------------------------
    def _build_pages(self) -> None:
        # Real views replace these placeholders as each feature lands.
        for key, label in SECTIONS:
            page = self._placeholder(label)
            self._pages[key] = page
            self.stack.addWidget(page)

    def _install_real_views(self) -> None:
        """Swap placeholders for real screens (grows as features land)."""
        if self.db is None:
            return
        from .calculator_view import CalculatorView
        from .order_entry_view import OrderEntryView
        from .settings_view import SettingsView

        entry = OrderEntryView(self.db)
        entry.order_saved.connect(self._on_order_saved)
        self.set_page("new_order", entry)

        calculator = CalculatorView(self.db)
        calculator.convert_requested.connect(self.open_calculator_conversion)
        self.set_page("calculator", calculator)

        settings = SettingsView(self.db)
        settings.settings_saved.connect(self._on_settings_changed)
        self.set_page("settings", settings)

    def _on_settings_changed(self) -> None:
        """Let other screens pick up new default rates when settings change."""
        for page in self._pages.values():
            hook = getattr(page, "on_settings_changed", None)
            if callable(hook):
                hook()

    def _refresh_data_views(self) -> None:
        for page in self._pages.values():
            hook = getattr(page, "refresh", None)
            if callable(hook):
                hook()

    def _on_order_saved(self, order_id: int) -> None:
        self._refresh_data_views()
        self.go_to("history")

    def open_order_for_edit(self, order) -> None:
        page = self._pages.get("new_order")
        if hasattr(page, "edit_order"):
            page.edit_order(order)
        self.go_to("new_order")

    def open_calculator_conversion(self, plates) -> None:
        page = self._pages.get("new_order")
        if hasattr(page, "prefill_from_calculator"):
            page.prefill_from_calculator(plates)
        self.go_to("new_order")

    def log_reprint(self, source_plate) -> None:
        """Open the reprint dialog for a saved plate and persist the result."""
        from .reprint_dialog import ReprintDialog

        dialog = ReprintDialog(source_plate, self.db.get_settings(), self)
        if dialog.exec() == QDialog.Accepted and dialog.result_plate is not None:
            self.db.add_plate(dialog.result_plate)
            self._refresh_data_views()

    def _placeholder(self, label: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(40, 40, 40, 40)
        title = QLabel(label)
        title.setObjectName("PageTitle")
        hint = QLabel("Not built yet.")
        hint.setObjectName("Muted")
        lay.addWidget(title)
        lay.addWidget(hint)
        lay.addStretch(1)
        return w

    def set_page(self, key: str, widget: QWidget) -> None:
        """Swap a placeholder for a real view (used as features are wired in)."""
        old = self._pages.get(key)
        idx = self.stack.indexOf(old) if old is not None else -1
        if idx != -1:
            self.stack.removeWidget(old)
            old.deleteLater()
        self._pages[key] = widget
        self.stack.insertWidget(idx if idx != -1 else self.stack.count(), widget)

    def _on_nav(self, key: str) -> None:
        # Clicking "New order" in the rail while editing an existing order
        # starts a fresh blank one; an in-progress new order is preserved.
        if key == "new_order":
            page = self._pages.get("new_order")
            hook = getattr(page, "ensure_new_mode", None)
            if callable(hook):
                hook()
        self.go_to(key)

    def go_to(self, key: str) -> None:
        page = self._pages.get(key)
        if page is not None:
            self.stack.setCurrentWidget(page)
        btn = self._nav_buttons.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
