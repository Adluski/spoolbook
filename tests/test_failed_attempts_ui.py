"""Qt-level tests for the failed-attempt entry UI (Run A).

Covers: failed_attempts_dialog.py in isolation, the plate row's FAILURES
button wiring, mark_complete_dialog's COGS figure, and the full
new-order -> log failure -> save -> reload -> edit -> save round trip that
mirrors the sequence 472c3a3 fixed for weight/print-time.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from PySide6.QtWidgets import QDialog

from spoolbook import calculations as calc
from spoolbook.database import Database
from spoolbook.models import FailedAttempt, Order, Plate
from spoolbook.ui.failed_attempts_dialog import FailedAttemptsDialog
from spoolbook.ui.mark_complete_dialog import MarkCompleteDialog
from spoolbook.ui.order_entry_view import OrderEntryView


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
    base = dict(
        plate_label="Base", weight_grams=100.0, print_time_minutes=60,
        material_type="PLA", material_source="own",
        material_rate_per_gram=0.90, machine_rate_per_hour=25.0,
    )
    base.update(kw)
    return Plate(**base)


def make_order(**kw):
    base = dict(
        title="Job", customer_name="Rahul",
        date_time=datetime(2026, 6, 1, 14, 30, 0),
        plates=[make_plate()],
    )
    base.update(kw)
    return Order(**base)


# -- FailedAttemptsDialog, in isolation (no exec()) --------------------------
def test_dialog_add_attempt_defaults_to_fifty_percent(qtbot):
    plate = make_plate()
    dialog = FailedAttemptsDialog(plate, 1)
    qtbot.addWidget(dialog)

    dialog._add_attempt()
    assert dialog._rows[0]["spin"].value() == 50


def test_dialog_live_footer_matches_calc_functions(qtbot):
    plate = make_plate()
    dialog = FailedAttemptsDialog(plate, 1)
    qtbot.addWidget(dialog)

    dialog._add_attempt()
    dialog._rows[0]["spin"].setValue(40)

    from spoolbook.ui.widgets import fmt_money
    temp_attempts = [FailedAttempt(completion_percent=40.0)]
    from dataclasses import replace
    temp = replace(plate, failed_attempts=temp_attempts)
    material = calc.plate_failed_material_cost(temp)
    machine = calc.plate_failed_machine_cost(temp)
    total = calc.plate_failed_cost(temp)
    assert dialog.summary.text() == (
        f"Wasted: material {fmt_money(material)} · machine {fmt_money(machine)} "
        f"· total {fmt_money(total)}"
    )


def test_dialog_remove_attempt_updates_footer(qtbot):
    plate = make_plate(failed_attempts=[
        FailedAttempt(completion_percent=20.0),
        FailedAttempt(completion_percent=80.0),
    ])
    dialog = FailedAttemptsDialog(plate, 1)
    qtbot.addWidget(dialog)

    assert len(dialog._rows) == 2
    entry_to_remove = dialog._rows[0]
    dialog._remove_row(entry_to_remove)

    assert len(dialog._rows) == 1
    assert dialog._rows[0]["label"].text() == "Attempt 1"
    # plate untouched until OK — this only affects the dialog's working copy.
    assert len(plate.failed_attempts) == 2


def test_dialog_cancel_leaves_plate_attempts_unchanged(qtbot):
    plate = make_plate(failed_attempts=[FailedAttempt(completion_percent=20.0)])
    original = list(plate.failed_attempts)
    dialog = FailedAttemptsDialog(plate, 1)
    qtbot.addWidget(dialog)

    dialog._add_attempt()
    dialog._rows[-1]["spin"].setValue(90)
    dialog.reject()

    assert plate.failed_attempts == original
    assert len(plate.failed_attempts) == 1


def test_dialog_ok_writes_back_with_positions_set(qtbot):
    plate = make_plate(failed_attempts=[FailedAttempt(completion_percent=20.0)])
    dialog = FailedAttemptsDialog(plate, 1)
    qtbot.addWidget(dialog)

    dialog._add_attempt()
    dialog._rows[-1]["spin"].setValue(40)
    dialog._on_accept()

    assert [a.completion_percent for a in plate.failed_attempts] == [20.0, 40.0]
    assert [a.position for a in plate.failed_attempts] == [0, 1]


# -- PlateRow: button label / tooltip states ---------------------------------
def test_failures_button_shows_dash_with_no_attempts(view):
    view.new_order()
    row = view.plate_editor._rows[0]
    assert row.failures_btn.text() == "—"


def test_failures_button_shows_count_when_attempts_exist(view):
    order = make_order()
    order.plates[0].failed_attempts = [
        FailedAttempt(completion_percent=20.0),
        FailedAttempt(completion_percent=50.0),
    ]
    view.edit_order(order)
    row = view.plate_editor._rows[0]
    assert row.failures_btn.text() == "2"


# -- PlateRow: dialog OK updates button, tooltip, cogs chip, and emits changed
def test_clicking_ok_updates_button_and_emits_changed(view, monkeypatch):
    order = make_order()
    view.edit_order(order)
    row = view.plate_editor._rows[0]

    def fake_exec(self):
        self._add_attempt()
        self._rows[-1]["spin"].setValue(40)
        self._on_accept()
        return QDialog.Accepted

    monkeypatch.setattr(FailedAttemptsDialog, "exec", fake_exec)

    seen = []
    row.changed.connect(lambda: seen.append(True))

    before_rollup = calc.order_rollup(view.order, view.settings)
    row.failures_btn.click()

    from spoolbook.ui.widgets import fmt_money
    assert row.failures_btn.text() == "1"
    assert row.plate.failed_attempts[0].completion_percent == 40.0
    assert row.failures_btn.toolTip() == f"Wasted: {fmt_money(calc.plate_failed_cost(row.plate))}"
    assert seen  # `changed` fired so the footer recomputes

    after_rollup = calc.order_rollup(view.order, view.settings)
    expected_delta = calc.plate_failed_cost(row.plate)
    assert after_rollup["total_cogs_for_order"] == pytest.approx(
        before_rollup["total_cogs_for_order"] + expected_delta)


def test_dialog_cancel_via_button_leaves_row_untouched(view, monkeypatch):
    order = make_order()
    view.edit_order(order)
    row = view.plate_editor._rows[0]

    def fake_exec(self):
        self._add_attempt()
        self.reject()
        return QDialog.Rejected

    monkeypatch.setattr(FailedAttemptsDialog, "exec", fake_exec)

    row.failures_btn.click()

    assert row.failures_btn.text() == "—"
    assert row.plate.failed_attempts == []


# -- mark_complete_dialog: displayed COGS is plate_cogs + plate_failed_cost --
def test_mark_complete_dialog_shows_cogs_plus_failed_cost(qtbot):
    from spoolbook.config import DEFAULT_SETTINGS
    order = make_order()
    order.plates[0].failed_attempts = [FailedAttempt(completion_percent=20.0)]
    settings = dict(DEFAULT_SETTINGS)
    dialog = MarkCompleteDialog(order, settings)
    qtbot.addWidget(dialog)

    total, _ = dialog._live_cogs()
    plate = order.plates[0]
    assert total == pytest.approx(calc.plate_cogs(plate) + calc.plate_failed_cost(plate))


# -- full round trip: the exact sequence that destroyed orders 24 and 28 -----
def test_full_roundtrip_new_order_log_failure_save_reload_edit_save(view, db, monkeypatch):
    view.new_order()
    row = view.plate_editor._rows[0]
    row.label_edit.setText("Base")
    row.weight.setValue(100.0)
    row.duration._hours.setValue(1)
    view.customer_edit.setText("Rahul")

    def fake_exec(self):
        self._add_attempt()
        self._rows[-1]["spin"].setValue(40)
        self._on_accept()
        return QDialog.Accepted

    monkeypatch.setattr(FailedAttemptsDialog, "exec", fake_exec)
    row.failures_btn.click()
    assert row.plate.failed_attempts[0].completion_percent == 40.0

    view._save()
    orders = db.list_orders()
    assert len(orders) == 1
    saved_id = orders[0].id

    reloaded = db.get_order(saved_id)
    assert len(reloaded.plates[0].failed_attempts) == 1
    assert reloaded.plates[0].failed_attempts[0].completion_percent == 40.0

    view.edit_order(reloaded)
    row2 = view.plate_editor._rows[0]
    assert row2.failures_btn.text() == "1"
    assert row2.plate.failed_attempts[0].completion_percent == 40.0

    view._save()
    reloaded_again = db.get_order(saved_id)
    assert len(reloaded_again.plates[0].failed_attempts) == 1
    assert reloaded_again.plates[0].failed_attempts[0].completion_percent == 40.0
