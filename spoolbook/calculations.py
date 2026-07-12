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


# --- order totals (cost of one unit as entered) ----------------------------
def total_material_cost(plates: Sequence[Plate]) -> float:
    return sum(plate_material_cost(p) for p in plates)


def total_machine_cost(plates: Sequence[Plate]) -> float:
    return sum(plate_machine_cost(p) for p in plates)


def total_cogs(plates: Sequence[Plate]) -> float:
    return sum(plate_cogs(p) for p in plates)


def total_cogs_for_order(order: Order) -> float:
    """Whole-job COGS: the per-unit total run order.quantity times."""
    return total_cogs(order.plates) * order.quantity


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
    """Split a per-run order price across plates proportional to each
    plate's COGS share (even split if total COGS is zero — mirrors
    plate_attributions' fallback), for seeding per-plate prices on a mode
    switch. Only plates without an existing price are included — a price
    already set by hand is never overwritten. ``order_price`` is a per-run
    figure; callers seeding from a whole-job price must divide by quantity
    first."""
    if not plates:
        return {}
    cogs_values = [plate_cogs(p) for p in plates]
    cogs_sum = sum(cogs_values)
    seeds = {}
    for i, (p, cogs) in enumerate(zip(plates, cogs_values)):
        if p.final_price is not None:
            continue
        share = (cogs / cogs_sum) if cogs_sum else (1.0 / len(plates))
        seeds[i] = order_price * share
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
        return per_plate_profit(order.plates) * order.quantity
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
        "total_cogs": cogs,
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
        return [
            {
                "material_type": p.material_type,
                "cogs": plate_cogs(p) * order.quantity,
                "revenue": (p.final_price or 0.0) * order.quantity,
                "profit": ((p.final_price or 0.0) - plate_cogs(p)) * order.quantity,
            }
            for p in plates
        ]

    order_revenue = order_final_price(order, settings)
    order_prof = order_profit(order, settings)
    cogs_values = [plate_cogs(p) for p in plates]
    cogs_sum = sum(cogs_values)

    rows = []
    for plate, cogs in zip(plates, cogs_values):
        share = (cogs / cogs_sum) if cogs_sum else (1.0 / len(plates))
        rows.append({
            "material_type": plate.material_type,
            "cogs": cogs,
            "revenue": order_revenue * share,
            "profit": order_prof * share,
        })
    return rows
