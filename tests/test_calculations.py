"""Tests for the pure costing / roll-up logic."""
import pytest

from spoolbook import calculations as calc
from spoolbook.config import DEFAULT_SETTINGS
from spoolbook.models import Order, Plate

SETTINGS = dict(DEFAULT_SETTINGS)  # markup 1.75, buffer 5%


def plate(**kw):
    base = dict(
        weight_grams=100.0, print_time_minutes=120, material_type="PLA",
        material_source="own", material_rate_per_gram=0.9,
        machine_rate_per_hour=30.0,
    )
    base.update(kw)
    return Plate(**base)


# -- per plate --------------------------------------------------------------
def test_material_cost_own_filament():
    assert calc.plate_material_cost(plate(weight_grams=100, material_rate_per_gram=0.9)) == 90.0


def test_material_cost_customer_supplied_is_zero():
    assert calc.plate_material_cost(plate(material_source="customer")) == 0.0


def test_machine_cost():
    # 120 min = 2h at 30/hr
    assert calc.plate_machine_cost(plate(print_time_minutes=120, machine_rate_per_hour=30)) == 60.0


def test_cogs_is_material_plus_machine():
    p = plate()  # 90 + 60
    assert calc.plate_cogs(p) == 150.0


def test_cogs_customer_supplied_is_machine_only():
    p = plate(material_source="customer")  # material 0 + machine 60
    assert calc.plate_cogs(p) == 60.0


# -- suggested price --------------------------------------------------------
def test_suggested_unit_price_formula():
    # cogs 150, material 90; (150 + 0.05*90) * 1.75 = 154.5 * 1.75
    p = plate()
    got = calc.suggested_unit_price([p], SETTINGS["markup_multiplier"],
                                    SETTINGS["pellet_buffer_percent"])
    assert got == pytest.approx(270.375)


def test_suggested_price_scales_with_quantity_and_discount():
    p = plate()
    unit = calc.suggested_unit_price([p], 1.75, 5.0)
    got = calc.suggested_price([p], 1.75, 5.0, quantity=3, bulk_discount_percent=10)
    assert got == pytest.approx(unit * 3 * 0.9)


def test_suggested_price_multi_plate_mixed_material():
    plates = [
        plate(material_type="PLA"),                       # cogs 150, mat 90
        plate(material_type="PETG", material_rate_per_gram=1.2,
              machine_rate_per_hour=40.0),                # mat 120, machine 80 => cogs 200
    ]
    # total cogs 350, total material 210; (350 + 0.05*210)*1.75
    assert calc.suggested_unit_price(plates, 1.75, 5.0) == pytest.approx((350 + 10.5) * 1.75)


# -- order-level roll-ups ---------------------------------------------------
def test_order_level_profit_defaults_to_price_minus_cogs():
    order = Order(pricing_mode="order_level", plates=[plate()])  # cogs 150
    order.final_price = 300.0
    # profit not set -> 300 - 150
    assert calc.order_profit(order, SETTINGS) == pytest.approx(150.0)


def test_order_level_profit_always_tracks_price_minus_cogs():
    # Profit is derived, so a stale/independent stored value must be ignored
    # and profit must move with the price.
    order = Order(pricing_mode="order_level", plates=[plate()], final_price=300.0)
    order.profit = 42.0  # deliberately unrelated to price - cogs
    assert calc.order_profit(order, SETTINGS) == pytest.approx(150.0)  # 300 - 150
    order.final_price = 999.0
    assert calc.order_profit(order, SETTINGS) == pytest.approx(849.0)  # 999 - 150


def test_order_level_profit_regression_manual_price_override():
    # Regression for the reported bug: 16 g, 2 h, PLA, own filament, with rate
    # snapshots that make COGS = ₹64.40. Final price was manually overridden to
    # ₹200, but a stale stored profit of ₹49.56 (the profit at the *suggested*
    # price) was displayed instead of ₹200 − ₹64.40 = ₹135.60.
    p = plate(weight_grams=16.0, print_time_minutes=120,
              material_type="PLA", material_source="own",
              material_rate_per_gram=0.90, machine_rate_per_hour=25.0)
    assert calc.plate_cogs(p) == pytest.approx(64.40)  # 14.40 material + 50.00 machine
    order = Order(pricing_mode="order_level", plates=[p], final_price=200.0)
    order.profit = 49.56  # the stale, wrong value the bug displayed
    assert calc.order_profit(order, SETTINGS) == pytest.approx(135.60)
    assert calc.order_rollup(order, SETTINGS)["profit"] == pytest.approx(135.60)


def test_order_level_price_defaults_to_suggested_when_unset():
    order = Order(pricing_mode="order_level", plates=[plate()])
    assert order.final_price is None
    assert calc.order_final_price(order, SETTINGS) == pytest.approx(270.375)


# -- per-plate roll-ups -----------------------------------------------------
def test_per_plate_price_and_profit_sum_plates():
    # Stored profit values (50, 30) are deliberately mismatched with
    # price - cogs (150) to prove they are ignored: profit is derived, not
    # trusted. Plate 1: 200 - 150 = 50 (coincides with stored). Plate 2:
    # 120 - 150 = -30 (does NOT coincide with the stored 30).
    order = Order(
        pricing_mode="per_plate",
        plates=[
            plate(final_price=200.0, profit=50.0),
            plate(final_price=120.0, profit=30.0),
        ],
    )
    assert calc.order_final_price(order, SETTINGS) == 320.0
    assert calc.order_profit(order, SETTINGS) == pytest.approx(20.0)  # 50 + (-30)


def test_per_plate_profit_ignores_stale_stored_value():
    # Mirrors test_order_level_profit_always_tracks_price_minus_cogs: a
    # stale/independent stored plate.profit must never be trusted.
    p = plate(final_price=200.0)  # cogs 150
    p.profit = 9999.0  # deliberately wrong stored value
    order = Order(pricing_mode="per_plate", plates=[p])
    assert calc.order_profit(order, SETTINGS) == pytest.approx(50.0)  # 200 - 150, not 9999


def test_per_plate_missing_price_reports_loss():
    # A plate with no price still burned material/machine time — profit must
    # show that loss, not silently read as zero.
    unpriced = plate(final_price=None)   # cogs 150
    priced = plate(final_price=100.0)    # cogs 150
    order = Order(pricing_mode="per_plate", plates=[unpriced, priced])
    assert calc.order_final_price(order, SETTINGS) == pytest.approx(100.0)
    # unpriced: 0 - 150 = -150; priced: 100 - 150 = -50 -> total -200
    assert calc.order_profit(order, SETTINGS) == pytest.approx(-200.0)


# -- attribution ------------------------------------------------------------
def test_attributions_sum_back_to_order_totals_order_level():
    order = Order(pricing_mode="order_level",
                  plates=[plate(material_type="PLA"),
                          plate(material_type="PETG", material_rate_per_gram=1.2,
                                machine_rate_per_hour=40.0)],
                  final_price=500.0, profit=150.0)
    rows = calc.plate_attributions(order, SETTINGS)
    assert sum(r["revenue"] for r in rows) == pytest.approx(500.0)
    assert sum(r["profit"] for r in rows) == pytest.approx(150.0)
    assert sum(r["cogs"] for r in rows) == pytest.approx(calc.total_cogs(order.plates))
    assert {r["material_type"] for r in rows} == {"PLA", "PETG"}


def test_attributions_even_split_when_zero_cogs():
    order = Order(pricing_mode="order_level",
                  plates=[plate(material_source="customer", print_time_minutes=0),
                          plate(material_source="customer", print_time_minutes=0)],
                  final_price=100.0, profit=100.0)
    rows = calc.plate_attributions(order, SETTINGS)
    assert rows[0]["revenue"] == pytest.approx(50.0)
    assert rows[1]["revenue"] == pytest.approx(50.0)


def test_empty_order_rollup_is_safe():
    order = Order(pricing_mode="order_level", plates=[])
    r = calc.order_rollup(order, SETTINGS)
    assert r["total_cogs"] == 0
    assert r["profit"] == pytest.approx(r["final_price"])  # 0 - 0
    assert calc.plate_attributions(order, SETTINGS) == []


# -- quantity scaling ---------------------------------------------------
# Explicit rates (0.90/g material, 25/h machine) so these never depend on
# saved settings, matching the reported-bug scenario: one plate at COGS 120.
def qty_plate(**kw):
    base = dict(
        weight_grams=100.0, print_time_minutes=72, material_type="PLA",
        material_source="own", material_rate_per_gram=0.90,
        machine_rate_per_hour=25.0,
    )
    base.update(kw)
    return Plate(**base)  # cogs = 90 material + 30 machine = 120


def test_total_cogs_for_order_scales_by_quantity():
    p = qty_plate()
    order = Order(plates=[p], quantity=3)
    assert calc.total_cogs(order.plates) == pytest.approx(120.0)  # per-unit, unchanged
    assert calc.total_cogs_for_order(order) == pytest.approx(360.0)


def test_total_cogs_for_order_qty_one_matches_total_cogs():
    p = qty_plate()
    order = Order(plates=[p], quantity=1)
    assert calc.total_cogs_for_order(order) == pytest.approx(calc.total_cogs(order.plates))


def test_order_level_profit_qty_one_unchanged():
    p = qty_plate()
    order = Order(pricing_mode="order_level", plates=[p], quantity=1, final_price=300.0)
    assert calc.order_profit(order, SETTINGS) == pytest.approx(300.0 - 120.0)


def test_order_level_profit_scales_cogs_with_quantity():
    # Regression for the reported bug: COGS 120, qty 3. Profit must subtract
    # COGS x3, not the unscaled per-unit COGS.
    p = qty_plate()
    order = Order(pricing_mode="order_level", plates=[p], quantity=3, final_price=1000.0)
    buggy_profit = 1000.0 - 120.0  # what the old code produced
    true_profit = 1000.0 - 120.0 * 3
    assert calc.order_profit(order, SETTINGS) == pytest.approx(true_profit)
    assert calc.order_profit(order, SETTINGS) != pytest.approx(buggy_profit)
    assert calc.order_rollup(order, SETTINGS)["profit"] == pytest.approx(true_profit)


def test_order_level_profit_scales_cogs_with_quantity_suggested_price():
    # Same as above but with the price left at the suggested (unset) value,
    # so both sides of the subtraction come from live formulas.
    p = qty_plate()
    order = Order(pricing_mode="order_level", plates=[p], quantity=3)
    price = calc.order_final_price(order, SETTINGS)
    assert calc.order_profit(order, SETTINGS) == pytest.approx(price - 120.0 * 3)


def test_attributions_sum_back_order_level_qty_gt_one():
    order = Order(
        pricing_mode="order_level", quantity=3, final_price=1500.0,
        plates=[qty_plate(material_type="PLA"),
                qty_plate(material_type="PETG", material_rate_per_gram=1.2,
                          machine_rate_per_hour=40.0)],
    )
    rows = calc.plate_attributions(order, SETTINGS)
    assert sum(r["revenue"] for r in rows) == pytest.approx(calc.order_final_price(order, SETTINGS))
    assert sum(r["profit"] for r in rows) == pytest.approx(calc.order_profit(order, SETTINGS))
    # order_level attribution "cogs" stays per-unit, matching order_rollup's
    # total_cogs convention.
    assert sum(r["cogs"] for r in rows) == pytest.approx(calc.total_cogs(order.plates))


def test_per_plate_final_price_and_profit_qty_one_unchanged():
    order = Order(
        pricing_mode="per_plate", quantity=1,
        plates=[qty_plate(final_price=200.0, profit=50.0),
                qty_plate(final_price=120.0, profit=30.0)],
    )
    assert calc.order_final_price(order, SETTINGS) == pytest.approx(320.0)
    assert calc.order_profit(order, SETTINGS) == pytest.approx(80.0)


def test_per_plate_final_price_and_profit_scale_with_quantity():
    order = Order(
        pricing_mode="per_plate", quantity=3,
        plates=[qty_plate(final_price=200.0, profit=50.0),
                qty_plate(final_price=120.0, profit=30.0)],
    )
    # Per-run sums are 320 revenue / 80 profit; the whole job runs 3x.
    assert calc.order_final_price(order, SETTINGS) == pytest.approx(320.0 * 3)
    assert calc.order_profit(order, SETTINGS) == pytest.approx(80.0 * 3)
    # The per-plate helpers themselves stay pure per-run sums.
    assert calc.per_plate_final_price(order.plates) == pytest.approx(320.0)
    assert calc.per_plate_profit(order.plates) == pytest.approx(80.0)


def test_attributions_sum_back_per_plate_qty_gt_one():
    order = Order(
        pricing_mode="per_plate", quantity=3,
        plates=[qty_plate(material_type="PLA", final_price=200.0, profit=50.0),
                qty_plate(material_type="PETG", material_rate_per_gram=1.2,
                          machine_rate_per_hour=40.0, final_price=120.0, profit=30.0)],
    )
    rows = calc.plate_attributions(order, SETTINGS)
    assert sum(r["revenue"] for r in rows) == pytest.approx(calc.order_final_price(order, SETTINGS))
    assert sum(r["profit"] for r in rows) == pytest.approx(calc.order_profit(order, SETTINGS))
    assert sum(r["cogs"] for r in rows) == pytest.approx(calc.total_cogs(order.plates) * order.quantity)
    # The stored profit values (50, 30) are stale/wrong; prove they are not
    # what produced the summed total.
    naive_stale_sum = (50.0 + 30.0) * order.quantity
    assert sum(r["profit"] for r in rows) != pytest.approx(naive_stale_sum)


# -- per-plate price seeding on mode switch ----------------------------------
def test_seed_per_plate_prices_splits_by_cogs_share_and_sums_to_order_price():
    p1 = qty_plate()                                                    # cogs 120
    p2 = qty_plate(material_type="PETG", material_rate_per_gram=1.2,
                   machine_rate_per_hour=40.0)                          # cogs 168
    seeds = calc.seed_per_plate_prices([p1, p2], 100.0)
    assert seeds[0] == pytest.approx(100.0 * 120 / 288)
    assert seeds[1] == pytest.approx(100.0 * 168 / 288)
    assert sum(seeds.values()) == pytest.approx(100.0)


def test_seed_per_plate_prices_even_split_when_zero_cogs():
    p1 = qty_plate(material_source="customer", print_time_minutes=0)
    p2 = qty_plate(material_source="customer", print_time_minutes=0)
    seeds = calc.seed_per_plate_prices([p1, p2], 100.0)
    assert seeds[0] == pytest.approx(50.0)
    assert seeds[1] == pytest.approx(50.0)


def test_seed_per_plate_prices_skips_already_priced_plates():
    already_priced = qty_plate(final_price=999.0)   # cogs 120, hand-set price
    unpriced = qty_plate()                           # cogs 120
    seeds = calc.seed_per_plate_prices([already_priced, unpriced], 100.0)
    assert 0 not in seeds
    assert seeds[1] == pytest.approx(50.0)  # equal cogs -> 50/50, only unpriced gets a seed


# -- money rounding ---------------------------------------------------------
def test_round_money_half_up():
    assert calc.round_money(270.375) == 270.38
    assert calc.round_money(1.005) == 1.01
    assert calc.round_money(2.5) == 2.5
