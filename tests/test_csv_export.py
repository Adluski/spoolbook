"""Tests for the plate-level CSV export."""
import csv
from datetime import datetime

from spoolbook.config import DEFAULT_SETTINGS
from spoolbook.csv_export import HEADERS, build_rows, write_csv
from spoolbook.models import Order, Plate

SETTINGS = dict(DEFAULT_SETTINGS)


def plate(**kw):
    base = dict(weight_grams=100.0, print_time_minutes=120, material_type="PLA",
                material_source="own", material_rate_per_gram=0.9,
                machine_rate_per_hour=30.0)
    base.update(kw)
    return Plate(**base)


def _orders():
    o1 = Order(id=1, customer_name="Rahul", title="Casing",
               date_time=datetime(2026, 6, 1, 14, 30), notes="orange\nPLA",
               pricing_mode="order_level", final_price=500.0, profit=200.0,
               plates=[plate(id=11, plate_label="Base"),
                       plate(id=12, plate_label="Lid", material_type="PETG",
                             material_rate_per_gram=1.2, machine_rate_per_hour=40.0)])
    o2 = Order(id=2, customer_name="Meena", title="Gear",
               date_time=datetime(2026, 6, 5, 9, 0), pricing_mode="per_plate",
               plates=[plate(id=21, final_price=250.0, profit=90.0)])
    return [o1, o2]


def test_one_row_per_plate():
    _, rows = build_rows(_orders(), SETTINGS)
    assert len(rows) == 3  # 2 plates + 1 plate


def test_order_fields_duplicated_across_plate_rows():
    headers, rows = build_rows(_orders(), SETTINGS)
    cust = headers.index("customer")
    title = headers.index("title")
    # First two rows belong to order 1 and repeat its customer/title.
    assert rows[0][cust] == rows[1][cust] == "Rahul"
    assert rows[0][title] == rows[1][title] == "Casing"
    assert rows[2][cust] == "Meena"


def test_plate_specific_columns_differ():
    headers, rows = build_rows(_orders(), SETTINGS)
    mat = headers.index("material")
    pcogs = headers.index("plate_cogs")
    assert rows[0][mat] == "PLA"
    assert rows[1][mat] == "PETG"
    assert rows[0][pcogs] == 150.0          # 90 + 60
    assert rows[1][pcogs] == 200.0          # 120 + 80


def test_plate_price_only_in_per_plate_mode():
    headers, rows = build_rows(_orders(), SETTINGS)
    price = headers.index("plate_price")
    assert rows[0][price] == ""             # order-level order -> blank
    assert rows[2][price] == 250.0          # per-plate order -> value


def test_notes_newlines_flattened():
    headers, rows = build_rows(_orders(), SETTINGS)
    notes = headers.index("notes")
    assert "\n" not in rows[0][notes]
    assert rows[0][notes] == "orange PLA"


def test_write_csv_roundtrip(tmp_path):
    path = tmp_path / "export.csv"
    count = write_csv(_orders(), SETTINGS, str(path))
    assert count == 3
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = list(csv.reader(fh))
    assert reader[0] == HEADERS
    assert len(reader) == 4  # header + 3 plate rows
