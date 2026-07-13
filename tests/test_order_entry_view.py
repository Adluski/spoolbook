"""Regression tests for the order-entry screen's load/save lifecycle.

These exist because edit_order() used to alias the caller's Order object and
a signal fired mid-load (plate_editor.set_pricing_mode -> changed ->
_recompute -> _sync_order_from_widgets) wrote the editor's still-blank state
straight back into it, corrupting both the in-memory Order and, if the user
then hit Save, the database row.
"""
from datetime import datetime

import pytest

from spoolbook.database import Database
from spoolbook.models import Order, Plate
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
        plate_label="Base", weight_grams=231.0, print_time_minutes=180,
        material_type="PLA", material_source="own",
        material_rate_per_gram=0.9, machine_rate_per_hour=30.0,
    )
    base.update(kw)
    return Plate(**base)


def make_order(**kw):
    base = dict(
        title="Battery casing x2", customer_name="Rahul",
        date_time=datetime(2026, 6, 1, 14, 30, 0), notes="orange PLA",
        plates=[
            make_plate(plate_label="Base", weight_grams=231.0),
            make_plate(plate_label="Lid", weight_grams=88.5, print_time_minutes=60),
        ],
    )
    base.update(kw)
    return Order(**base)


# -- the core regression ------------------------------------------------------
def test_edit_order_after_new_order_preserves_plates(view):
    view.new_order()  # editor now holds one blank row
    order = make_order()
    view.edit_order(order)

    editor_plates = view.plate_editor.plates()
    assert [p.weight_grams for p in editor_plates] == [231.0, 88.5]
    assert [p.print_time_minutes for p in editor_plates] == [180, 60]
    assert [p.plate_label for p in editor_plates] == ["Base", "Lid"]

    assert [p.weight_grams for p in view.order.plates] == [231.0, 88.5]
    assert [p.plate_label for p in view.order.plates] == ["Base", "Lid"]


def test_edit_order_does_not_mutate_callers_order(view):
    view.new_order()
    order = make_order()
    original_weights = [p.weight_grams for p in order.plates]
    original_labels = [p.plate_label for p in order.plates]

    view.edit_order(order)
    # Mutate the view's copy and confirm the caller's object is unaffected.
    view.plate_editor.plates()[0].weight_grams = 0.0

    assert [p.weight_grams for p in order.plates] == original_weights
    assert [p.plate_label for p in order.plates] == original_labels
    assert view.order is not order


def test_edit_order_preserves_order_id_for_save(view, db):
    order = make_order()
    order_id = db.save_order(order)

    view.new_order()
    loaded = db.get_order(order_id)
    view.edit_order(loaded)

    assert view.order.id == order_id


# -- round trip: the exact sequence that destroyed real orders ---------------
def test_new_type_save_reload_edit_save_roundtrip(view, db, qtbot):
    view.new_order()
    row = view.plate_editor._rows[0]
    row.label_edit.setText("Base")
    row.weight.setValue(231.0)
    # set_minutes() blocks signals (it's meant for programmatic population);
    # drive the sub-spinboxes directly so _commit() actually fires, like a
    # real keystroke would.
    row.duration._hours.setValue(3)
    view.customer_edit.setText("Rahul")

    view._save()
    orders = db.list_orders()
    assert len(orders) == 1
    saved_id = orders[0].id

    reloaded = db.get_order(saved_id)
    assert reloaded.plates[0].weight_grams == 231.0

    view.edit_order(reloaded)
    assert view.plate_editor.plates()[0].weight_grams == 231.0

    view._save()
    reloaded_again = db.get_order(saved_id)
    assert reloaded_again.plates[0].weight_grams == 231.0
    assert reloaded_again.plates[0].print_time_minutes == 180


# -- per-plate mode -----------------------------------------------------------
def test_edit_order_per_plate_mode_preserves_final_price(view):
    order = make_order(pricing_mode="per_plate")
    order.plates[0].final_price = 45.0
    order.plates[0].profit = 20.0
    order.plates[1].final_price = 15.0
    order.plates[1].profit = 5.0

    view.new_order()
    view.edit_order(order)

    prices = [p.final_price for p in view.plate_editor.plates()]
    assert prices == [45.0, 15.0]
