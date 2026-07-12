#!/usr/bin/env python3
"""One-time importer for the founder's historical print orders.

Reads ``historical_orders.csv`` (one order per row) and inserts, for each row,
one completed order-level Order with exactly one linked Plate. It writes to the
same SQLite file the app uses (``config.db_path()`` / ``$SPOOLBOOK_DB``), so the
orders show up in History and the Dashboard on the next launch.

Deliberately does **not** set profit on the order or the plate: the app derives
order-level profit as ``final_price - COGS`` every time it is read
(``calculations.resolved_order_level_profit`` ignores any stored snapshot). We
leave those fields NULL so this backfill cannot reintroduce the profit-drift bug
that was just fixed — profit is always recomputed from the price and the plate's
own rate snapshot.

Usage:
    python import_historical_orders.py [historical_orders.csv] [--force]

The importer refuses to run if the target database already contains real
(non-scratch) orders, so an accidental second run can't silently double the
totals. Pass --force to import anyway (e.g. into a throwaway DB via
``SPOOLBOOK_DB=/tmp/test.db``).
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime

from spoolbook import calculations
from spoolbook.config import CURRENCY, db_path
from spoolbook.database import Database
from spoolbook.models import Order, Plate

CSV_COLUMNS = [
    "order_title", "customer_name", "date", "weight_grams",
    "print_time_minutes", "material_type", "material_source",
    "material_rate_per_gram", "machine_rate_per_hour", "final_price", "notes",
]

# Every backdated order gets a fixed, arbitrary clock time; only the date is
# real. Noon keeps it clear of date-boundary/timezone edge cases.
DEFAULT_TIME = (12, 0, 0)


def parse_date(raw: str) -> datetime:
    """Accept an ISO date (``YYYY-MM-DD``) or a bare Excel serial number."""
    raw = raw.strip()
    try:
        d = datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        # Fallback: Excel 1900-system serial, in case a raw export is used.
        from datetime import timedelta
        d = datetime(1899, 12, 30) + timedelta(days=int(float(raw)))
    return d.replace(hour=DEFAULT_TIME[0], minute=DEFAULT_TIME[1],
                     second=DEFAULT_TIME[2], microsecond=0)


def build_order(row: dict) -> Order:
    """Map one CSV row to an Order carrying exactly one Plate."""
    plate = Plate(
        weight_grams=float(row["weight_grams"] or 0),
        print_time_minutes=int(float(row["print_time_minutes"] or 0)),
        material_type=row["material_type"].strip(),
        material_source=row["material_source"].strip(),
        material_rate_per_gram=float(row["material_rate_per_gram"] or 0),
        machine_rate_per_hour=float(row["machine_rate_per_hour"] or 0),
        # final_price / profit stay None: order-level pricing lives on the order.
    )
    return Order(
        title=row["order_title"].strip(),
        customer_name=row["customer_name"].strip(),
        date_time=parse_date(row["date"]),
        notes=(row.get("notes") or "").strip(),
        pricing_mode="order_level",
        status="completed",
        final_price=float(row["final_price"] or 0),
        # profit deliberately left None -> derived on read as final_price - COGS.
        plates=[plate],
    )


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]
    csv_path = args[0] if args else "historical_orders.csv"

    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = set(CSV_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            print(f"ERROR: {csv_path} is missing columns: {sorted(missing)}")
            return 1
        rows = list(reader)

    if not rows:
        print(f"ERROR: {csv_path} has no data rows.")
        return 1

    target = db_path()
    db = Database(target)

    existing = db.list_orders(include_scratch=False)
    if existing and not force:
        print(f"ERROR: {target} already holds {len(existing)} order(s).")
        print("Refusing to import — a second run would duplicate every order.")
        print("Re-run with --force, or point $SPOOLBOOK_DB at a fresh file.")
        db.close()
        return 1

    settings = db.get_settings()
    inserted_ids: list[int] = []
    for row in rows:
        order = build_order(row)
        inserted_ids.append(db.save_order(order))

    # Read the orders back from the DB and let the app's own calculation layer
    # derive every number, so this summary matches exactly what History and the
    # Dashboard will show.
    print(f"\nImported into: {target}")
    print(f"Rows read from {csv_path}: {len(rows)}\n")
    header = f"{'#':>2}  {'date':<10}  {'customer':<12}  {'title':<32}  " \
             f"{'revenue':>9}  {'COGS':>8}  {'profit':>9}"
    print(header)
    print("-" * len(header))

    total_rev = total_cogs = total_profit = 0.0
    for n, oid in enumerate(inserted_ids, start=1):
        o = db.get_order(oid)
        rev = calculations.order_final_price(o, settings)
        cogs = calculations.total_cogs(o.plates)
        profit = calculations.order_profit(o, settings)  # = rev - cogs, derived
        total_rev += rev
        total_cogs += cogs
        total_profit += profit
        print(f"{n:>2}  {o.date_time.date().isoformat():<10}  "
              f"{o.customer_name[:12]:<12}  {o.title[:32]:<32}  "
              f"{rev:>9.2f}  {cogs:>8.2f}  {profit:>9.2f}")

    db.close()

    m = calculations.round_money
    print("\n" + "=" * 40)
    print("IMPORT SUMMARY")
    print("=" * 40)
    print(f"  Total orders inserted : {len(inserted_ids)}")
    print(f"  Total revenue         : {CURRENCY}{m(total_rev):,.2f}")
    print(f"  Total COGS            : {CURRENCY}{m(total_cogs):,.2f}")
    print(f"  Total profit          : {CURRENCY}{m(total_profit):,.2f}")
    # Sanity: profit is derived, never stored — this identity must hold.
    print(f"  (revenue - COGS)      : {CURRENCY}{m(total_rev - total_cogs):,.2f}")
    print("=" * 40)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
