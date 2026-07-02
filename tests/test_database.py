"""Tests for the SQLite persistence layer."""
from datetime import datetime

import pytest

from spoolbook.config import DEFAULT_SETTINGS
from spoolbook.database import Database
from spoolbook.models import Order, Plate


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


def make_plate(**kw):
    base = dict(
        weight_grams=100.0, print_time_minutes=120, material_type="PLA",
        material_source="own", material_rate_per_gram=0.9,
        machine_rate_per_hour=30.0,
    )
    base.update(kw)
    return Plate(**base)


# -- settings ---------------------------------------------------------------
def test_settings_seeded_to_defaults(db):
    assert db.get_settings() == DEFAULT_SETTINGS


def test_update_settings_persists_and_reloads(tmp_path):
    path = tmp_path / "s.db"
    db = Database(path)
    db.update_settings({"markup_multiplier": 2.0, "pla_rate_per_gram": 1.1})
    db.close()

    reopened = Database(path)
    settings = reopened.get_settings()
    assert settings["markup_multiplier"] == 2.0
    assert settings["pla_rate_per_gram"] == 1.1
    # Untouched keys keep their defaults.
    assert settings["petg_rate_per_gram"] == DEFAULT_SETTINGS["petg_rate_per_gram"]
    reopened.close()


# -- orders + plates --------------------------------------------------------
def test_save_and_get_order_roundtrip(db):
    order = Order(
        title="Battery casing x2", customer_name="Rahul",
        date_time=datetime(2026, 6, 1, 14, 30, 0), notes="orange PLA",
        plates=[
            make_plate(plate_label="Base", weight_grams=80.5),
            make_plate(plate_label="Lid", material_type="PETG",
                       material_rate_per_gram=1.2, machine_rate_per_hour=40.0),
        ],
    )
    order_id = db.save_order(order)
    assert order_id is not None

    loaded = db.get_order(order_id)
    assert loaded.customer_name == "Rahul"
    assert loaded.date_time == datetime(2026, 6, 1, 14, 30, 0)
    assert len(loaded.plates) == 2
    assert [p.plate_label for p in loaded.plates] == ["Base", "Lid"]
    # Rate snapshots survive the roundtrip exactly.
    assert loaded.plates[1].material_rate_per_gram == 1.2
    assert loaded.plates[0].weight_grams == 80.5


def test_backdating_is_preserved(db):
    order = Order(date_time=datetime(2020, 1, 2, 9, 0, 0), plates=[make_plate()])
    oid = db.save_order(order)
    assert db.get_order(oid).date_time == datetime(2020, 1, 2, 9, 0, 0)


def test_edit_reconciles_plates_and_preserves_ids(db):
    order = Order(plates=[make_plate(plate_label="A"), make_plate(plate_label="B")])
    db.save_order(order)
    keep_id = order.plates[0].id

    # Remove B, edit A, add C.
    order.plates[0].plate_label = "A-edited"
    order.plates = [order.plates[0], make_plate(plate_label="C")]
    db.save_order(order)

    loaded = db.get_order(order.id)
    labels = [p.plate_label for p in loaded.plates]
    assert labels == ["A-edited", "C"]
    # Kept plate retained its id; removed plate is gone.
    assert loaded.plates[0].id == keep_id


def test_delete_order_cascades_to_plates(db):
    order = Order(plates=[make_plate(), make_plate()])
    db.save_order(order)
    db.delete_order(order.id)
    assert db.get_order(order.id) is None
    remaining = db.conn.execute("SELECT COUNT(*) c FROM plates").fetchone()["c"]
    assert remaining == 0


def test_reprint_link_set_null_when_source_deleted(db):
    order = Order(plates=[make_plate(plate_label="orig")])
    db.save_order(order)
    source_id = order.plates[0].id

    reprint = make_plate(plate_label="reprint", is_reprint=True,
                         linked_plate_id=source_id, order_id=order.id)
    reprint_id = db.add_plate(reprint)

    db.delete_plate(source_id)
    assert db.get_plate(reprint_id).linked_plate_id is None


# -- listing / filtering ----------------------------------------------------
def test_list_orders_filters(db):
    db.save_order(Order(customer_name="Anita",
                        date_time=datetime(2026, 1, 10, 10, 0, 0),
                        plates=[make_plate(material_type="PLA")]))
    db.save_order(Order(customer_name="Bala",
                        date_time=datetime(2026, 3, 15, 10, 0, 0),
                        plates=[make_plate(material_type="PETG")]))
    db.save_order(Order(customer_name="Anita Jr",
                        date_time=datetime(2026, 5, 20, 10, 0, 0),
                        plates=[make_plate(material_type="PLA", is_reprint=True)]))

    assert len(db.list_orders()) == 3
    assert len(db.list_orders(customer="anita")) == 2
    assert len(db.list_orders(material="PETG")) == 1
    assert len(db.list_orders(reprint_only=True)) == 1
    ranged = db.list_orders(start=datetime(2026, 2, 1),
                            end=datetime(2026, 4, 1))
    assert len(ranged) == 1
    assert ranged[0].customer_name == "Bala"


def test_scratch_orders_excluded_by_default(db):
    db.save_order(Order(customer_name="real", plates=[make_plate()]))
    db.save_order(Order(customer_name="scratch", is_scratch=True,
                        plates=[make_plate()]))
    assert len(db.list_orders()) == 1
    assert len(db.list_orders(include_scratch=True)) == 2
