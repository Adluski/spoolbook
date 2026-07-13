"""CSV export — one row per PLATE.

Order-level fields (customer, title, date, order price/profit …) are repeated
on every plate row of that order, so the export keeps full plate-level
granularity while remaining a flat, spreadsheet-friendly table.
"""
from __future__ import annotations

import csv
from typing import Sequence

from . import calculations as calc
from .config import MATERIAL_SOURCE_LABELS
from .models import Order

HEADERS = [
    # order-level (duplicated per plate)
    "order_id", "date", "customer", "title", "notes", "pricing_mode",
    "quantity", "bulk_discount_%", "order_cogs", "order_price",
    "order_profit", "order_margin_%",
    # plate-level
    "plate_id", "plate_label", "is_reprint", "reprint_of_plate_id",
    "material", "source", "weight_g", "print_time_min",
    "material_rate_per_g", "machine_rate_per_hr",
    "plate_material_cost", "plate_machine_cost", "plate_cogs",
    "failed_attempt_count", "failed_attempt_percents",
    "failed_material_cost", "failed_machine_cost", "failed_cogs",
    "plate_price", "plate_profit",
]


def _fmt_percent(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value)


def _m(value) -> float:
    return calc.round_money(value)


def build_rows(orders: Sequence[Order], settings: dict) -> tuple[list[str], list[list]]:
    """Return (headers, rows) with one row per plate."""
    rows: list[list] = []
    for order in orders:
        rollup = calc.order_rollup(order, settings)
        order_cells = [
            order.id,
            order.date_time.strftime("%Y-%m-%d %H:%M"),
            order.customer_name,
            order.title,
            order.notes.replace("\n", " ").strip(),
            order.pricing_mode,
            order.quantity,
            order.bulk_discount_percent,
            _m(rollup["total_cogs_for_order"]),  # whole-job COGS, includes failures
            _m(rollup["final_price"]),
            _m(rollup["profit"]),
            round(rollup["margin_percent"], 1),
        ]
        per_plate = order.pricing_mode == "per_plate"

        if not order.plates:
            rows.append(order_cells + [""] * (len(HEADERS) - len(order_cells)))
            continue

        for plate in order.plates:
            rows.append(order_cells + [
                plate.id,
                plate.plate_label,
                "yes" if plate.is_reprint else "no",
                plate.linked_plate_id if plate.linked_plate_id else "",
                plate.material_type,
                MATERIAL_SOURCE_LABELS.get(plate.material_source, plate.material_source),
                round(plate.weight_grams, 2),
                plate.print_time_minutes,
                plate.material_rate_per_gram,
                plate.machine_rate_per_hour,
                _m(calc.plate_material_cost(plate)),
                _m(calc.plate_machine_cost(plate)),
                _m(calc.plate_cogs(plate)),
                len(plate.failed_attempts),
                ";".join(_fmt_percent(a.completion_percent) for a in plate.failed_attempts),
                _m(calc.plate_failed_material_cost(plate)),
                _m(calc.plate_failed_machine_cost(plate)),
                _m(calc.plate_failed_cost(plate)),
                _m(plate.final_price) if (per_plate and plate.final_price is not None) else "",
                _m(plate.profit) if (per_plate and plate.profit is not None) else "",
            ])
    return HEADERS, rows


def write_csv(orders: Sequence[Order], settings: dict, path: str) -> int:
    """Write the plate-level CSV to ``path``; return the number of plate rows."""
    headers, rows = build_rows(orders, settings)
    # utf-8-sig so Excel reads names/notes with unicode correctly.
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        writer.writerows(rows)
    return len(rows)
