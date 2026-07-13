"""Pure costing and roll-up logic.

No Qt, no SQLite, no globals — every function takes the numbers it needs and
returns a result, so the same code powers the live scratch calculator, the
order screen, history and the dashboard. Rates always come from the plate's
own snapshot (never from live settings), except when *suggesting* a price for
a brand-new order, where the markup/buffer are read from current settings.

Values are returned unrounded; round only at the display edge with
``round_money`` so sums of rounded parts never drift from a rounded sum.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

from .models import Order, Plate


def round_money(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# --- per plate -------------------------------------------------------------
def plate_material_cost(plate: Plate) -> float:
    """Filament cost. Zero when the customer supplied the material."""
    if plate.material_source == "customer":
        return 0.0
    return plate.weight_grams * plate.material_rate_per_gram


def plate_machine_cost(plate: Plate) -> float:
    return (plate.print_time_minutes / 60.0) * plate.machine_rate_per_hour


def plate_cogs(plate: Plate) -> float:
    return plate_material_cost(plate) + plate_machine_cost(plate)


# --- failed attempts ---------------------------------------------------------
# A failed attempt is wasted consumption layered on top of a normally priced,
# always-delivered plate — never a discount on that plate's own revenue, and
# never scaled by order.quantity (it burned material/machine time exactly
# once). Pro-rated against the PLATE's own snapshotted rates, never the
# order's totals.
def failed_attempt_material_cost(plate: Plate, attempt) -> float:
    if plate.material_source == "customer":
        return 0.0
    pct = attempt.completion_percent / 100.0
    return plate.weight_grams * pct * plate.material_rate_per_gram


def failed_attempt_machine_cost(plate: Plate, attempt) -> float:
    pct = attempt.completion_percent / 100.0
    return (plate.print_time_minutes / 60.0) * pct * plate.machine_rate_per_hour


def failed_attempt_cost(plate: Plate, attempt) -> float:
    return failed_attempt_material_cost(plate, attempt) + failed_attempt_machine_cost(plate, attempt)


def plate_failed_material_cost(plate: Plate) -> float:
    return sum(failed_attempt_material_cost(plate, a) for a in plate.failed_attempts)


def plate_failed_machine_cost(plate: Plate) -> float:
    return sum(failed_attempt_machine_cost(plate, a) for a in plate.failed_attempts)


def plate_failed_cost(plate: Plate) -> float:
    return plate_failed_material_cost(plate) + plate_failed_machine_cost(plate)


def total_failed_material_cost(plates: Sequence[Plate]) -> float:
    return sum(plate_failed_material_cost(p) for p in plates)


def total_failed_machine_cost(plates: Sequence[Plate]) -> float:
    return sum(plate_failed_machine_cost(p) for p in plates)


def total_failed_cost(plates: Sequence[Plate]) -> float:
    return sum(plate_failed_cost(p) for p in plates)


# --- order totals (cost of one unit as entered) ----------------------------
def total_material_cost(plates: Sequence[Plate]) -> float:
    return sum(plate_material_cost(p) for p in plates)


def total_machine_cost(plates: Sequence[Plate]) -> float:
    return sum(plate_machine_cost(p) for p in plates)


def total_cogs(plates: Sequence[Plate]) -> float:
    return sum(plate_cogs(p) for p in plates)


def total_cogs_for_order(order: Order) -> float:
    """Whole-job COGS: delivered plates scale with quantity, failed attempts
    don't — each is a single logged event that burned material/machine time
    exactly once, regardless of how many units were ordered."""
    return total_cogs(order.plates) * order.quantity + total_failed_cost(order.plates)


# --- suggested pricing -----------------------------------------------------
def suggested_unit_price(
    plates: Sequence[Plate],
    markup_multiplier: float,
    pellet_buffer_percent: float,
) -> float:
    """Spec formula: (COGS + buffer%·material) · markup — for one unit."""
    cogs = total_cogs(plates)
    material = total_material_cost(plates)
    base = cogs + (pellet_buffer_percent / 100.0) * material
    return base * markup_multiplier


def apply_quantity_discount(
    unit_price: float, quantity: int, bulk_discount_percent: float
) -> float:
    return unit_price * quantity * (1 - bulk_discount_percent / 100.0)


def suggested_price(
    plates: Sequence[Plate],
    markup_multiplier: float,
    pellet_buffer_percent: float,
    quantity: int = 1,
    bulk_discount_percent: float = 0.0,
) -> float:
    """Suggested price for the whole order (unit price scaled by quantity and
    any bulk discount). This is what pre-fills an order's final_price."""
    unit = suggested_unit_price(plates, markup_multiplier, pellet_buffer_percent)
    return apply_quantity_discount(unit, quantity, bulk_discount_percent)


# --- per-plate mode roll-ups ----------------------------------------------
def per_plate_final_price(plates: Sequence[Plate]) -> float:
    return sum((p.final_price or 0.0) for p in plates)


def seed_per_plate_prices(plates: Sequence[Plate], order_price: float) -> dict[int, float]:
    """Split what's LEFT of a per-run order price, after already-priced
    plates, across the still-unpriced plates — proportional to each
    unpriced plate's COGS share of the UNPRICED plates' COGS total (even
    split if that total is zero — mirrors plate_attributions' fallback).

    Only plates without an existing price are included in the result — a
    price already set by hand is never overwritten, and its value is
    subtracted from order_price before the remainder is divided up, so
    ``sum(seeded values) + sum(already-set prices) == order_price``.
    A hand-priced order can exceed order_price; the remainder then clamps
    to 0 rather than seeding a negative price. ``order_price`` is a
    per-run figure; callers seeding from a whole-job price must divide by
    quantity first."""
    if not plates:
        return {}
    priced_total = sum(p.final_price for p in plates if p.final_price is not None)
    remainder = max(0.0, order_price - priced_total)
    unpriced = [(i, p) for i, p in enumerate(plates) if p.final_price is None]
    if not unpriced:
        return {}
    cogs_values = {i: plate_cogs(p) for i, p in unpriced}
    cogs_sum = sum(cogs_values.values())
    seeds = {}
    for i, _p in unpriced:
        share = (cogs_values[i] / cogs_sum) if cogs_sum else (1.0 / len(unpriced))
        seeds[i] = remainder * share
    return seeds


def per_plate_profit(plates: Sequence[Plate]) -> float:
    """Profit is always price − COGS, never the independently stored
    snapshot (see plate.profit's docstring — it exists only as a
    persisted snapshot of this same subtraction)."""
    return sum((p.final_price or 0.0) - plate_cogs(p) for p in plates)


# --- mode-aware order roll-ups --------------------------------------------
def _settings_markup(settings: dict) -> tuple[float, float]:
    return settings["markup_multiplier"], settings["pellet_buffer_percent"]


def resolved_order_level_price(order: Order, settings: dict) -> float:
    """Order-level final price: the manual override if set, else suggested."""
    if order.final_price is not None:
        return order.final_price
    markup, buffer = _settings_markup(settings)
    return suggested_price(order.plates, markup, buffer,
                           order.quantity, order.bulk_discount_percent)


def resolved_order_level_profit(order: Order, settings: dict) -> float:
    """Order-level profit is always final price − COGS.

    It is a derived quantity, never an independent override: a manually set
    final price is reflected in profit immediately, so the two can never drift
    apart. Any value stored in ``order.profit`` is ignored here on purpose —
    it exists only as a persisted snapshot of this same subtraction.
    """
    return resolved_order_level_price(order, settings) - total_cogs_for_order(order)


def order_final_price(order: Order, settings: dict) -> float:
    if order.pricing_mode == "per_plate":
        return per_plate_final_price(order.plates) * order.quantity
    return resolved_order_level_price(order, settings)


def order_profit(order: Order, settings: dict) -> float:
    if order.pricing_mode == "per_plate":
        # NOT per_plate_profit(plates) * qty: that would subtract failed
        # cost qty times. Failed cost is subtracted once, via
        # total_cogs_for_order.
        return per_plate_final_price(order.plates) * order.quantity - total_cogs_for_order(order)
    return resolved_order_level_profit(order, settings)


def margin_percent(revenue: float, profit: float) -> float:
    return (profit / revenue * 100.0) if revenue else 0.0


def order_rollup(order: Order, settings: dict) -> dict:
    """Everything the UI needs to show for one order, in one call."""
    markup, buffer = _settings_markup(settings)
    cogs = total_cogs(order.plates)
    final_price = order_final_price(order, settings)
    profit = order_profit(order, settings)
    return {
        "total_material_cost": total_material_cost(order.plates),
        "total_machine_cost": total_machine_cost(order.plates),
        "total_cogs": cogs,  # unchanged: per-run, delivered-only
        "total_failed_cost": total_failed_cost(order.plates),  # never scaled by quantity
        "total_failed_material_cost": total_failed_material_cost(order.plates),
        "total_failed_machine_cost": total_failed_machine_cost(order.plates),
        "total_cogs_for_order": total_cogs_for_order(order),  # whole-job, incl. failures
        "suggested_unit_price": suggested_unit_price(order.plates, markup, buffer),
        "suggested_price": suggested_price(
            order.plates, markup, buffer, order.quantity,
            order.bulk_discount_percent),
        "final_price": final_price,
        "profit": profit,
        "margin_percent": margin_percent(final_price, profit),
    }


# --- per-material attribution (dashboard) ----------------------------------
def plate_attributions(order: Order, settings: dict) -> list[dict]:
    """Attribute the order's revenue/profit/COGS down to each plate.

    In per_plate mode the plate's own price/profit are exact. In order_level
    mode the order totals are split across plates in proportion to each
    plate's COGS (evenly if total COGS is zero), so the dashboard can group by
    material even when pricing was set at the order level.
    """
    plates = order.plates
    if not plates:
        return []

    if order.pricing_mode == "per_plate":
        rows = []
        for p in plates:
            revenue = (p.final_price or 0.0) * order.quantity
            cogs = plate_cogs(p) * order.quantity + plate_failed_cost(p)
            rows.append({
                "material_type": p.material_type,
                "cogs": cogs,
                "revenue": revenue,
                "profit": revenue - cogs,
            })
        return rows

    order_revenue = order_final_price(order, settings)
    # The revenue/profit split is weighted by DELIVERED-plate COGS only: a
    # plate that failed must not attract a bigger revenue share for it.
    cogs_values = [plate_cogs(p) for p in plates]
    cogs_sum = sum(cogs_values)

    rows = []
    for plate, cogs in zip(plates, cogs_values):
        share = (cogs / cogs_sum) if cogs_sum else (1.0 / len(plates))
        row_cogs = cogs * order.quantity + plate_failed_cost(plate)
        row_revenue = order_revenue * share
        rows.append({
            "material_type": plate.material_type,
            "cogs": row_cogs,
            "revenue": row_revenue,
            # Derived per row, not order_prof * share: keeps profit ==
            # revenue - cogs exactly even when a failure makes a plate's
            # cost share diverge from its revenue share.
            "profit": row_revenue - row_cogs,
        })
    return rows
