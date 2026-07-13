"""Tests for the plate-level CSV export."""
import csv
from datetime import datetime

from spoolbook.config import DEFAULT_SETTINGS
from spoolbook.csv_export import HEADERS, build_rows, write_csv
from spoolbook.models import FailedAttempt, Order, Plate

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


def test_failed_attempt_columns_present_with_failures():
    o = Order(id=3, customer_name="Failed Co", title="Bracket",
              date_time=datetime(2026, 6, 10, 12, 0), pricing_mode="order_level",
              final_price=450.0,
              plates=[plate(id=31, weight_grams=100.0, print_time_minutes=60,
                            material_rate_per_gram=0.90, machine_rate_per_hour=25.0,
                            failed_attempts=[FailedAttempt(completion_percent=20.0)]),
                      plate(id=32, weight_grams=100.0, print_time_minutes=60,
                            material_rate_per_gram=0.90, machine_rate_per_hour=25.0)])
    headers, rows = build_rows([o], SETTINGS)
    count = headers.index("failed_attempt_count")
    percents = headers.index("failed_attempt_percents")
    fmat = headers.index("failed_material_cost")
    fmach = headers.index("failed_machine_cost")
    fcogs = headers.index("failed_cogs")
    order_cogs = headers.index("order_cogs")

    assert rows[0][count] == 1
    assert rows[0][percents] == "20"
    assert rows[0][fmat] == 18.0
    assert rows[0][fmach] == 5.0
    assert rows[0][fcogs] == 23.0
    # order_cogs comes from the roll-up and includes the failed cost: 230 base + 23
    assert rows[0][order_cogs] == 253.0
    assert rows[1][order_cogs] == 253.0


def test_failed_attempt_columns_blank_for_no_failures():
    _, rows = build_rows(_orders(), SETTINGS)
    headers, _ = build_rows(_orders(), SETTINGS)
    count = headers.index("failed_attempt_count")
    percents = headers.index("failed_attempt_percents")
    fcogs = headers.index("failed_cogs")
    assert rows[0][count] == 0
    assert rows[0][percents] == ""
    assert rows[0][fcogs] == 0.0


def test_multiple_failed_attempt_percents_joined():
    o = Order(id=4, pricing_mode="order_level", final_price=100.0,
              plates=[plate(id=41, failed_attempts=[
                  FailedAttempt(completion_percent=10.0),
                  FailedAttempt(completion_percent=60.0),
              ])])
    headers, rows = build_rows([o], SETTINGS)
    percents = headers.index("failed_attempt_percents")
    assert rows[0][percents] == "10;60"


def test_write_csv_roundtrip(tmp_path):
    path = tmp_path / "export.csv"
    count = write_csv(_orders(), SETTINGS, str(path))
    assert count == 3
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = list(csv.reader(fh))
    assert reader[0] == HEADERS
    assert len(reader) == 4  # header + 3 plate rows
