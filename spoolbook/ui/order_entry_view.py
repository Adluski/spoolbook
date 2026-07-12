"""Create / edit an order with one or more plates.

The pricing-mode toggle visibly changes what is editable: in order-level mode
the summary bar's final-price and profit are the editable numbers (and the
per-plate price/profit columns hide); in per-plate mode those columns become
editable and the summary shows their totals read-only.

Order-level final price defaults to the suggested price but is a manual
override: once you touch it, it stops tracking the suggestion. Profit is always
derived (final price − COGS) and shown read-only, so it can never drift away
from the price.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate, QDateTime, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDateTimeEdit,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import calculations as calc
from ..models import Order, Plate
from .plate_editor import PlateRowsEditor
from .widgets import (
    Panel,
    SegmentedToggle,
    StatChip,
    field_label,
    fmt_money,
    hline,
    int_spin,
    money_spin,
    plain_double_spin,
    section_label,
)


def _to_qdatetime(dt: datetime) -> QDateTime:
    return QDateTime(QDate(dt.year, dt.month, dt.day),
                     QTime(dt.hour, dt.minute, dt.second))


def _from_qdatetime(qdt: QDateTime) -> datetime:
    d, t = qdt.date(), qdt.time()
    return datetime(d.year(), d.month(), d.day(), t.hour(), t.minute(), t.second())


class OrderEntryView(QWidget):
    order_saved = Signal(int)

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.settings = db.get_settings()
        self.order = Order()
        self._final_touched = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_topbar())
        outer.addWidget(self._build_scroll(), 1)
        outer.addWidget(self._build_summary())

        self._wire()
        self.new_order()

    # -- top bar ------------------------------------------------------------
    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(32, 20, 32, 16)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title_label = QLabel("New order")
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QLabel("Cost a job across one or more plates.")
        self.subtitle_label.setObjectName("PageSubtitle")
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        lay.addLayout(titles)
        lay.addStretch(1)
        self.blank_btn = QPushButton("Start blank")
        self.blank_btn.setObjectName("SecondaryButton")
        self.blank_btn.setCursor(Qt.PointingHandCursor)
        self.blank_btn.clicked.connect(self.new_order)
        lay.addWidget(self.blank_btn)
        return bar

    # -- scrollable body ----------------------------------------------------
    def _build_scroll(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("BodyScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(32, 12, 32, 20)
        lay.setSpacing(18)

        lay.addWidget(self._build_fields())
        lay.addWidget(self._build_plates_section())
        lay.addStretch(1)

        scroll.setWidget(content)
        return scroll

    def _build_fields(self) -> Panel:
        panel = Panel()
        grid = QGridLayout(panel)
        grid.setContentsMargins(22, 18, 22, 18)
        grid.setHorizontalSpacing(40)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)

        # left column — identity
        left = QFormLayout()
        left.setHorizontalSpacing(16)
        left.setVerticalSpacing(8)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("e.g. Battery casing ×2")
        self.customer_edit = QLineEdit()
        self.customer_edit.setPlaceholderText("Customer name")
        self.datetime_edit = QDateTimeEdit()
        self.datetime_edit.setCalendarPopup(True)
        self.datetime_edit.setDisplayFormat("dd MMM yyyy   hh:mm")
        left.addRow(field_label("Title"), self.title_edit)
        left.addRow(field_label("Customer"), self.customer_edit)
        left.addRow(field_label("Date & time"), self.datetime_edit)
        grid.addLayout(left, 0, 0)

        # right column — notes + bulk
        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(field_label("Notes"))
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Colour, phone number, delivery notes…")
        self.notes_edit.setFixedHeight(58)
        right.addWidget(self.notes_edit)

        bulk = QHBoxLayout()
        bulk.setSpacing(16)
        qty_box = QVBoxLayout()
        qty_box.setSpacing(3)
        qty_box.addWidget(field_label("Quantity"))
        self.quantity_spin = int_spin(1, 100_000)
        self.quantity_spin.setValue(1)
        self.quantity_spin.setFixedWidth(90)
        qty_box.addWidget(self.quantity_spin)
        disc_box = QVBoxLayout()
        disc_box.setSpacing(3)
        disc_box.addWidget(field_label("Bulk discount"))
        self.discount_spin = plain_double_spin(0, 100, decimals=1, step=1, suffix=" %")
        self.discount_spin.setFixedWidth(90)
        disc_box.addWidget(self.discount_spin)
        bulk.addLayout(qty_box)
        bulk.addLayout(disc_box)
        bulk.addStretch(1)
        right.addLayout(bulk)
        grid.addLayout(right, 0, 1)

        return panel

    def _build_plates_section(self) -> Panel:
        panel = Panel()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(22, 16, 22, 10)
        head.addWidget(section_label("Plates"))
        head.addStretch(1)
        head.addWidget(QLabel("Pricing"))
        self.pricing_toggle = SegmentedToggle([
            ("order_level", "Order-level"),
            ("per_plate", "Per-plate"),
        ])
        head.addWidget(self.pricing_toggle)
        lay.addLayout(head)
        lay.addWidget(hline())

        self.plate_editor = PlateRowsEditor(self.settings, "order_level")
        lay.addWidget(self.plate_editor)
        return panel

    # -- summary bar --------------------------------------------------------
    def _build_summary(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("SummaryBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(32, 12, 32, 12)
        lay.setSpacing(10)

        self.chip_material = StatChip("Material")
        self.chip_machine = StatChip("Machine")
        self.chip_cogs = StatChip("Total COGS")
        self.chip_suggested = StatChip("Suggested")
        for chip in (self.chip_material, self.chip_machine,
                     self.chip_cogs, self.chip_suggested):
            lay.addWidget(chip)

        lay.addStretch(1)

        # order-level editable controls
        self.ol_controls = QWidget()
        ol = QHBoxLayout(self.ol_controls)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(12)
        ol.addLayout(self._labeled("Final price", self._make_price_editor()))
        ol.addLayout(self._labeled("Profit", self._make_profit_editor()))
        self.margin_label_ol = QLabel("—")
        self.margin_label_ol.setObjectName("MarginValue")
        ol.addLayout(self._labeled("Margin", self.margin_label_ol))
        lay.addWidget(self.ol_controls)

        # per-plate read-outs
        self.pp_controls = QWidget()
        pp = QHBoxLayout(self.pp_controls)
        pp.setContentsMargins(0, 0, 0, 0)
        pp.setSpacing(10)
        self.chip_pp_price = StatChip("Order price", value_name="StatValueStrong")
        self.chip_pp_profit = StatChip("Profit", value_name="StatValueStrong")
        self.chip_pp_margin = StatChip("Margin")
        pp.addWidget(self.chip_pp_price)
        pp.addWidget(self.chip_pp_profit)
        pp.addWidget(self.chip_pp_margin)
        lay.addWidget(self.pp_controls)

        # save
        save_col = QVBoxLayout()
        save_col.setSpacing(3)
        self.error_label = QLabel("")
        self.error_label.setObjectName("StatusError")
        save_col.addWidget(self.error_label, 0, Qt.AlignRight)
        self.queue_check = QCheckBox("Save to print queue (planned print)")
        self.queue_check.setToolTip(
            "Store this as a planned print in the Queue instead of a realized "
            "order. Queued prints are excluded from the dashboard until you "
            "mark them complete.")
        self.queue_check.toggled.connect(self._on_queue_toggle)
        save_col.addWidget(self.queue_check, 0, Qt.AlignRight)
        self.save_btn = QPushButton("Save order")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self._save)
        save_col.addWidget(self.save_btn)
        lay.addLayout(save_col)
        return bar

    def _on_queue_toggle(self, queued: bool) -> None:
        self.save_btn.setText("Save to queue" if queued else "Save order")

    def _labeled(self, caption: str, widget: QWidget) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(2)
        cap = QLabel(caption.upper())
        cap.setObjectName("StatCaption")
        box.addWidget(cap)
        box.addWidget(widget)
        return box

    def _make_price_editor(self) -> QWidget:
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        self.final_spin = money_spin(minimum=0, maximum=100_000_000)
        self.final_spin.setFixedWidth(106)
        reset = QPushButton("↺")
        reset.setObjectName("ResetButton")
        reset.setFixedWidth(26)
        reset.setToolTip("Reset price & profit to suggested")
        reset.setCursor(Qt.PointingHandCursor)
        reset.clicked.connect(self._reset_to_suggested)
        h.addWidget(self.final_spin)
        h.addWidget(reset)
        return wrap

    def _make_profit_editor(self) -> QWidget:
        # Profit is derived (final price − COGS), so it is shown read-only and
        # can never be edited into disagreement with the price.
        self.profit_spin = money_spin(minimum=-100_000_000, maximum=100_000_000)
        self.profit_spin.setFixedWidth(106)
        self.profit_spin.setReadOnly(True)
        self.profit_spin.setFocusPolicy(Qt.NoFocus)
        self.profit_spin.setObjectName("DerivedSpin")
        return self.profit_spin

    # -- wiring -------------------------------------------------------------
    def _wire(self) -> None:
        self.plate_editor.changed.connect(self._recompute)
        self.pricing_toggle.changed.connect(self._on_mode_changed)
        self.quantity_spin.valueChanged.connect(self._recompute)
        self.discount_spin.valueChanged.connect(self._recompute)
        self.final_spin.valueChanged.connect(self._on_final_edited)

    # -- state sync -----------------------------------------------------------
    def _sync_order_from_widgets(self) -> None:
        """Push live widget values into self.order so calc functions that
        need a full Order (plates, quantity, final_price) see the current
        on-screen state."""
        self.order.plates = self.plate_editor.plates()
        self.order.quantity = self.quantity_spin.value()
        self.order.bulk_discount_percent = self.discount_spin.value()
        if self.order.pricing_mode == "order_level":
            self.order.final_price = round(self.final_spin.value(), 2) if self._final_touched else None

    # -- modes --------------------------------------------------------------
    def _on_mode_changed(self, mode: str) -> None:
        seed_prices = None
        if mode == "per_plate":
            # Seed blank per-plate prices from their share of the current
            # order-level price (one run — the roll-up re-applies quantity)
            # before switching, so unpriced plates don't silently read as 0.
            self._sync_order_from_widgets()
            qty = self.order.quantity if self.order.quantity >= 1 else 1
            order_price = calc.resolved_order_level_price(self.order, self.settings) / qty
            seed_prices = calc.seed_per_plate_prices(self.order.plates, order_price)
        self.order.pricing_mode = mode
        self.plate_editor.set_pricing_mode(mode, seed_prices)
        self._apply_mode_visibility(mode)
        self._recompute()

    def _apply_mode_visibility(self, mode: str) -> None:
        order_level = mode == "order_level"
        self.ol_controls.setVisible(order_level)
        self.pp_controls.setVisible(not order_level)
        self.chip_suggested.setVisible(order_level)

    # -- recompute ----------------------------------------------------------
    def _recompute(self) -> None:
        self._sync_order_from_widgets()
        rollup = calc.order_rollup(self.order, self.settings)
        qty = self.order.quantity

        # These chips are always PER-UNIT by design (order_rollup's
        # total_cogs convention) — do not scale them by quantity.
        self.chip_material.set_value(fmt_money(rollup["total_material_cost"]))
        self.chip_machine.set_value(fmt_money(rollup["total_machine_cost"]))
        self.chip_cogs.set_value(fmt_money(rollup["total_cogs"]))
        self.chip_suggested.set_value(fmt_money(rollup["suggested_price"]), tone="accent")
        self.chip_cogs.setToolTip(
            f"Per unit — order quantity is ×{qty}" if qty > 1 else "")

        # final_price / profit / margin are WHOLE-JOB (x quantity) figures.
        if self.order.pricing_mode == "order_level":
            if not self._final_touched:
                self._set_spin(self.final_spin, calc.round_money(rollup["final_price"]))
            final = rollup["final_price"]
            profit = rollup["profit"]
            # Profit always tracks the price — it is never an independent value.
            self._set_spin(self.profit_spin, calc.round_money(profit))
            self._set_margin(self.margin_label_ol, final, profit)
        else:
            final = rollup["final_price"]
            profit = rollup["profit"]
            self.chip_pp_price.set_value(fmt_money(final), tone="accent")
            self.chip_pp_profit.set_value(
                fmt_money(profit), tone="positive" if profit >= 0 else "negative")
            self.chip_pp_margin.set_value(f"{rollup['margin_percent']:.1f}%")

    def _set_spin(self, spin, value) -> None:
        spin.blockSignals(True)
        spin.setValue(value)
        spin.blockSignals(False)

    def _set_margin(self, label, revenue, profit) -> None:
        pct = calc.margin_percent(revenue, profit)
        label.setText(f"{pct:.1f}%")
        tone = "positive" if profit >= 0 else "negative"
        label.setProperty("tone", tone)
        label.style().unpolish(label)
        label.style().polish(label)

    def _on_final_edited(self) -> None:
        # Editing the price re-derives profit through the roll-up (final −
        # quantity-scaled COGS), so the two can never drift apart.
        self._final_touched = True
        self._recompute()

    def _reset_to_suggested(self) -> None:
        self._final_touched = False
        self._recompute()

    # -- load states --------------------------------------------------------
    def new_order(self) -> None:
        self.settings = self.db.get_settings()
        self.order = Order(date_time=datetime.now())
        self._final_touched = False
        self.title_label.setText("New order")
        self.title_edit.clear()
        self.customer_edit.clear()
        self.notes_edit.clear()
        self.datetime_edit.setDateTime(_to_qdatetime(self.order.date_time))
        self.quantity_spin.setValue(1)
        self.discount_spin.setValue(0)
        self.queue_check.setChecked(False)
        self.error_label.clear()
        self.pricing_toggle.set_value("order_level")
        self.order.pricing_mode = "order_level"
        self.plate_editor.set_settings(self.settings)
        self.plate_editor.set_pricing_mode("order_level")
        self.plate_editor.set_plates([])
        self.plate_editor.add_plate()  # start with one empty plate
        self._apply_mode_visibility("order_level")
        self._recompute()

    def prefill_from_calculator(self, plates: list[Plate]) -> None:
        """Open a fresh order pre-filled with calculated plates (convert flow)."""
        self.new_order()
        self.plate_editor.set_plates(plates or [])
        self._recompute()
        self.customer_edit.setFocus()

    def edit_order(self, order: Order) -> None:
        self.settings = self.db.get_settings()
        self.order = order
        self.title_label.setText(f"Edit order #{order.id}")
        self.title_edit.setText(order.title)
        self.customer_edit.setText(order.customer_name)
        self.notes_edit.setPlainText(order.notes)
        self.datetime_edit.setDateTime(_to_qdatetime(order.date_time))
        self.quantity_spin.setValue(order.quantity)
        self.discount_spin.setValue(order.bulk_discount_percent)
        self.queue_check.setChecked(order.status == "queued")
        self.error_label.clear()
        self.pricing_toggle.set_value(order.pricing_mode)
        self.plate_editor.set_settings(self.settings)
        self.plate_editor.set_pricing_mode(order.pricing_mode)
        self.plate_editor.set_plates([p for p in order.plates])
        self._apply_mode_visibility(order.pricing_mode)
        if order.pricing_mode == "order_level":
            # A stored final price is respected as-is; mark it touched so
            # recompute does not clobber it. Profit is re-derived from it.
            self._final_touched = order.final_price is not None
            if order.final_price is not None:
                self._set_spin(self.final_spin, order.final_price)
        self._recompute()

    def ensure_new_mode(self) -> None:
        """Called when the rail's New-order item is clicked while editing."""
        if self.order.id is not None:
            self.new_order()

    def on_settings_changed(self) -> None:
        self.settings = self.db.get_settings()
        self.plate_editor.set_settings(self.settings)

    # -- save ---------------------------------------------------------------
    def _save(self) -> None:
        plates = self.plate_editor.plates()
        if not self.customer_edit.text().strip():
            self._error("Enter a customer name to save the order.")
            self.customer_edit.setFocus()
            return
        if not plates:
            self._error("Add at least one plate.")
            return

        o = self.order
        o.title = self.title_edit.text().strip()
        o.customer_name = self.customer_edit.text().strip()
        o.notes = self.notes_edit.toPlainText().strip()
        o.date_time = _from_qdatetime(self.datetime_edit.dateTime())
        o.quantity = self.quantity_spin.value()
        o.bulk_discount_percent = self.discount_spin.value()
        o.pricing_mode = self.pricing_toggle.value()
        o.status = "queued" if self.queue_check.isChecked() else "completed"
        o.is_scratch = False
        o.plates = plates

        if o.pricing_mode == "order_level":
            o.final_price = round(self.final_spin.value(), 2)
            o.profit = round(self.profit_spin.value(), 2)
            for p in plates:
                p.final_price = None
                p.profit = None
        else:
            o.final_price = None
            o.profit = None
            # plate.final_price / profit already committed by the row editors.

        order_id = self.db.save_order(o)
        self.order_saved.emit(order_id)
        self.new_order()

    def _error(self, message: str) -> None:
        self.error_label.setText(message)
