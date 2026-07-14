"""pytest-qt coverage for the whole-job footer, WASTED chip, grams cycle,
the Breakdown button, and the cost-breakdown dialog (Run B)."""
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from spoolbook import calculations as calc
from spoolbook.database import Database
from spoolbook.models import FailedAttempt, Order, Plate
from spoolbook.ui.cost_breakdown_dialog import CostBreakdownDialog
from spoolbook.ui.order_entry_view import OrderEntryView
from spoolbook.ui.widgets import fmt_money


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


@pytest.fixture
def view(qtbot, db):
    v = OrderEntryView(db)
    qtbot.addWidget(v)
    return v


def make_plate(**kw):
    # cogs = 90 material + 30 machine = 120; 100 g, 72 min.
    base = dict(
        plate_label="Base", weight_grams=100.0, print_time_minutes=72,
        material_type="PLA", material_source="own",
        material_rate_per_gram=0.9, machine_rate_per_hour=25.0,
    )
    base.update(kw)
    return Plate(**base)


def make_order(**kw):
    base = dict(title="Casing", customer_name="Rahul",
                date_time=datetime(2026, 6, 1, 12, 0, 0),
                plates=[make_plate()])
    base.update(kw)
    return Order(**base)


# -- whole-job footer --------------------------------------------------------
def test_footer_shows_whole_job_cogs_not_per_unit(view):
    order = make_order(quantity=3)   # per-unit COGS 120 -> whole-job 360
    view.edit_order(order)
    assert view.chip_cogs._value.text() == fmt_money(360.0)
    assert view.chip_cogs._value.text() != fmt_money(120.0)
    # material/machine chips are whole-job too: 90*3 = 270, 30*3 = 90.
    assert view.chip_material._value.text() == fmt_money(270.0)
    assert view.chip_machine._value.text() == fmt_money(90.0)
    # the ×qty caption suffix makes the whole-job scale explicit.
    assert "×3" in view.chip_cogs._caption.text()


# -- WASTED chip -------------------------------------------------------------
def test_wasted_chip_zero_when_no_failures(view):
    view.edit_order(make_order(quantity=1))
    assert not view.chip_wasted.isHidden()          # always shown
    assert view.chip_wasted._value.text() == fmt_money(0.0)
    assert view.chip_wasted.property("dim") == "true"   # muted/inactive


def test_wasted_chip_shows_cost_when_failure_present(view):
    p = make_plate()
    p.failed_attempts = [FailedAttempt(completion_percent=50.0)]  # 45 mat + 15 mach
    view.edit_order(make_order(plates=[p], quantity=1))
    assert view.chip_wasted._value.text() == fmt_money(60.0)
    assert view.chip_wasted.property("dim") != "true"   # active tone
    assert view.chip_wasted._subtitle.text() != "—"


# -- Breakdown button visibility ---------------------------------------------
def test_breakdown_button_hidden_at_qty_one_no_failures(view):
    view.edit_order(make_order(quantity=1))
    assert view.breakdown_btn.isHidden()


def test_breakdown_button_shown_when_qty_gt_one(view):
    view.edit_order(make_order(quantity=2))
    assert not view.breakdown_btn.isHidden()


def test_breakdown_button_shown_when_failure_at_qty_one(view):
    p = make_plate()
    p.failed_attempts = [FailedAttempt(completion_percent=25.0)]
    view.edit_order(make_order(plates=[p], quantity=1))
    assert not view.breakdown_btn.isHidden()


# -- grams cycle -------------------------------------------------------------
def test_material_grams_cycle_leaves_money_unchanged(view):
    view.edit_order(make_order(quantity=3))
    money = view.chip_material._value.text()

    assert view._grams_cycle == "total"          # default on load
    view.chip_material.clicked.emit()
    assert view._grams_cycle == "own"
    view.chip_material.clicked.emit()
    assert view._grams_cycle == "supplied"
    view.chip_material.clicked.emit()
    assert view._grams_cycle == "total"          # wraps back

    # The money figure never moved through any of it.
    assert view.chip_material._value.text() == money
    # The subtitle DID track the cycle state.
    assert "total" in view.chip_material._subtitle.text()


def test_grams_cycle_resets_to_total_on_reload(view):
    view.edit_order(make_order(quantity=2))
    view.chip_material.clicked.emit()
    assert view._grams_cycle == "own"
    view.edit_order(make_order(quantity=2))
    assert view._grams_cycle == "total"


# -- dialog totals foot ------------------------------------------------------
def test_breakdown_dialog_totals_foot(qtbot):
    settings = {"markup_multiplier": 1.75, "pellet_buffer_percent": 5.0}
    own = make_plate()
    own.failed_attempts = [FailedAttempt(completion_percent=50.0)]
    cust = make_plate(plate_label="Lid", material_source="customer",
                      weight_grams=80.0, print_time_minutes=40)
    cust.failed_attempts = [FailedAttempt(completion_percent=30.0)]
    order = make_order(plates=[own, cust], quantity=3, final_price=1500.0)

    dialog = CostBreakdownDialog(order, settings)
    qtbot.addWidget(dialog)

    per_run = calc.total_cogs(order.plates)
    wasted = calc.total_failed_cost(order.plates)
    total = calc.total_cogs_for_order(order)
    # The identity the dialog renders in its TOTALS section must hold.
    assert per_run * order.quantity + wasted == pytest.approx(total)


# -- right-click entry (smoke) -----------------------------------------------
def test_breakdown_opens_from_queue_right_click(qtbot, db, monkeypatch):
    from spoolbook.ui import cost_breakdown_dialog, queue_view
    # Don't block on a modal event loop in the test.
    monkeypatch.setattr(cost_breakdown_dialog.CostBreakdownDialog, "exec",
                        lambda self: None)

    order = make_order(status="queued", quantity=2)
    db.save_order(order)
    v = queue_view.QueueView(db, MagicMock())
    qtbot.addWidget(v)

    item = v.tree.topLevelItem(0)
    assert item is not None
    # The exact slot the "Cost breakdown…" menu action calls — no crash.
    v._show_breakdown(item.order)


def test_breakdown_opens_from_history_right_click(qtbot, db, monkeypatch):
    from spoolbook.ui import cost_breakdown_dialog, history_view
    monkeypatch.setattr(cost_breakdown_dialog.CostBreakdownDialog, "exec",
                        lambda self: None)

    order = make_order(status="completed", quantity=1)
    db.save_order(order)
    v = history_view.HistoryView(db, MagicMock())
    qtbot.addWidget(v)

    item = v.tree.topLevelItem(0)
    assert item is not None
    v._show_breakdown(item.order)
