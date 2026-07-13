"""Tests for failed-attempt cost tracking (schema/model/calc layer only).

Written first, per spec: these must FAIL against the pre-implementation code,
then pass once FailedAttempt / the new calculations are added.
"""
import pytest

from spoolbook import calculations as calc
from spoolbook.config import DEFAULT_SETTINGS
from spoolbook.models import FailedAttempt, Order, Plate

SETTINGS = dict(DEFAULT_SETTINGS)


def plate(**kw):
    base = dict(
        weight_grams=100.0, print_time_minutes=72, material_type="PLA",
        material_source="own", material_rate_per_gram=0.90,
        machine_rate_per_hour=25.0,
    )
    base.update(kw)
    return Plate(**base)  # cogs = 90 material + 30 machine = 120


# -- the worked example, verbatim -------------------------------------------
def test_worked_example_failed_attempt_pro_rated_to_own_plate():
    p1 = Plate(weight_grams=100.0, print_time_minutes=60, material_source="own",
               material_rate_per_gram=0.90, machine_rate_per_hour=25.0,
               failed_attempts=[FailedAttempt(completion_percent=20.0)])
    p2 = Plate(weight_grams=100.0, print_time_minutes=60, material_source="own",
               material_rate_per_gram=0.90, machine_rate_per_hour=25.0)
    order = Order(pricing_mode="order_level", plates=[p1, p2], quantity=1, final_price=450.0)

    assert calc.total_material_cost(order.plates) == pytest.approx(180.0)
    assert calc.total_machine_cost(order.plates) == pytest.approx(50.0)
    assert calc.total_cogs(order.plates) == pytest.approx(230.0)  # delivered-only, unchanged

    assert calc.total_failed_cost(order.plates) == pytest.approx(23.0)  # 18 material + 5 machine
    assert calc.total_cogs_for_order(order) == pytest.approx(253.0)
    assert calc.order_profit(order, SETTINGS) == pytest.approx(197.0)


def test_worked_example_rejects_whole_order_percentage_bug():
    # The explicitly-wrong prior bug: 20% of the WHOLE order's COGS (230),
    # not just plate 1's own figures. That gives COGS 276 / profit 174.
    p1 = Plate(weight_grams=100.0, print_time_minutes=60, material_source="own",
               material_rate_per_gram=0.90, machine_rate_per_hour=25.0,
               failed_attempts=[FailedAttempt(completion_percent=20.0)])
    p2 = Plate(weight_grams=100.0, print_time_minutes=60, material_source="own",
               material_rate_per_gram=0.90, machine_rate_per_hour=25.0)
    order = Order(pricing_mode="order_level", plates=[p1, p2], quantity=1, final_price=450.0)

    assert calc.total_cogs_for_order(order) != pytest.approx(276.0)
    assert calc.order_profit(order, SETTINGS) != pytest.approx(174.0)


# -- accumulation on one plate -----------------------------------------------
def test_two_failed_attempts_accumulate():
    p = plate(failed_attempts=[
        FailedAttempt(completion_percent=10.0),
        FailedAttempt(completion_percent=60.0),
    ])
    # attempt 1: material 9 + machine 3 = 12; attempt 2: material 54 + machine 18 = 72
    assert calc.plate_failed_cost(p) == pytest.approx(84.0)


# -- customer-supplied material ----------------------------------------------
def test_failed_attempt_customer_supplied_material_is_zero():
    p = plate(material_source="customer",
              failed_attempts=[FailedAttempt(completion_percent=50.0)])
    assert calc.plate_failed_material_cost(p) == 0.0
    assert calc.plate_failed_machine_cost(p) == pytest.approx(15.0)  # 30 * 0.5
    assert calc.plate_failed_cost(p) == pytest.approx(15.0)


# -- boundary percentages ------------------------------------------------------
def test_full_failure_equals_full_plate_cost():
    p = plate(failed_attempts=[FailedAttempt(completion_percent=100.0)])
    assert calc.plate_failed_cost(p) == pytest.approx(calc.plate_cogs(p))


def test_near_zero_failure_is_near_zero_cost():
    p = plate(failed_attempts=[FailedAttempt(completion_percent=1.0)])
    assert calc.plate_failed_cost(p) == pytest.approx(calc.plate_cogs(p) * 0.01)


# -- quantity interaction: the easiest thing to get wrong ---------------------
def test_quantity_scaling_with_one_failed_attempt_order_level():
    p = plate(failed_attempts=[FailedAttempt(completion_percent=20.0)])  # base cogs 120
    order = Order(pricing_mode="order_level", plates=[p], quantity=3, final_price=1000.0)
    # delivered cogs scaled by qty: 120 * 3 = 360
    # failed cost NOT scaled: material 90*0.2=18, machine 30*0.2=6 -> 24
    assert calc.total_failed_cost(order.plates) == pytest.approx(24.0)
    assert calc.total_cogs_for_order(order) == pytest.approx(384.0)
    assert calc.order_profit(order, SETTINGS) == pytest.approx(1000.0 - 384.0)


def test_quantity_scaling_with_one_failed_attempt_per_plate():
    p = plate(final_price=200.0, failed_attempts=[FailedAttempt(completion_percent=20.0)])
    order = Order(pricing_mode="per_plate", plates=[p], quantity=3)
    assert calc.order_final_price(order, SETTINGS) == pytest.approx(600.0)  # 200*3
    # delivered cogs*3 (360) + failed cost once (24)
    assert calc.order_profit(order, SETTINGS) == pytest.approx(600.0 - 360.0 - 24.0)


def test_zero_failed_attempts_matches_pre_failure_behavior():
    p = plate()
    order = Order(pricing_mode="order_level", plates=[p], quantity=3, final_price=1000.0)
    assert calc.total_failed_cost(order.plates) == 0.0
    assert calc.total_cogs_for_order(order) == pytest.approx(360.0)
    assert calc.order_profit(order, SETTINGS) == pytest.approx(1000.0 - 360.0)


# -- attributions: sum back to order totals, qty>1, with failures -------------
def test_attributions_sum_back_with_failures_order_level():
    p1 = plate(material_type="PLA", failed_attempts=[FailedAttempt(completion_percent=20.0)])
    p2 = plate(material_type="PETG", material_rate_per_gram=1.2, machine_rate_per_hour=40.0)
    order = Order(pricing_mode="order_level", quantity=3, final_price=1500.0, plates=[p1, p2])
    rows = calc.plate_attributions(order, SETTINGS)
    assert sum(r["revenue"] for r in rows) == pytest.approx(calc.order_final_price(order, SETTINGS))
    assert sum(r["profit"] for r in rows) == pytest.approx(calc.order_profit(order, SETTINGS))
    assert sum(r["cogs"] for r in rows) == pytest.approx(calc.total_cogs_for_order(order))


def test_attributions_sum_back_with_failures_per_plate():
    p1 = plate(material_type="PLA", final_price=200.0,
               failed_attempts=[FailedAttempt(completion_percent=20.0)])
    p2 = plate(material_type="PETG", material_rate_per_gram=1.2,
               machine_rate_per_hour=40.0, final_price=120.0)
    order = Order(pricing_mode="per_plate", quantity=3, plates=[p1, p2])
    rows = calc.plate_attributions(order, SETTINGS)
    assert sum(r["revenue"] for r in rows) == pytest.approx(calc.order_final_price(order, SETTINGS))
    assert sum(r["profit"] for r in rows) == pytest.approx(calc.order_profit(order, SETTINGS))
    assert sum(r["cogs"] for r in rows) == pytest.approx(calc.total_cogs_for_order(order))


def test_failed_plate_does_not_get_larger_revenue_share():
    p_failed = plate(material_type="PLA", failed_attempts=[FailedAttempt(completion_percent=90.0)])
    p_ok = plate(material_type="PETG")
    with_fail = Order(pricing_mode="order_level", final_price=1000.0, plates=[p_failed, p_ok])

    p1 = plate(material_type="PLA")
    p2 = plate(material_type="PETG")
    without_fail = Order(pricing_mode="order_level", final_price=1000.0, plates=[p1, p2])

    rows_fail = calc.plate_attributions(with_fail, SETTINGS)
    rows_ok = calc.plate_attributions(without_fail, SETTINGS)
    # Both plates have identical base COGS, so absent any failure-driven bias
    # the revenue split is 50/50 either way — the failure must not move it.
    assert rows_fail[0]["revenue"] == pytest.approx(rows_ok[0]["revenue"])
    assert rows_fail[0]["revenue"] == pytest.approx(500.0)


# -- row identity: profit == revenue - cogs, qty>1 with failures, both modes --
def test_row_profit_equals_revenue_minus_cogs_order_level_qty_gt_one_with_failures():
    p1 = plate(material_type="PLA", failed_attempts=[FailedAttempt(completion_percent=20.0)])
    p2 = plate(material_type="PETG", material_rate_per_gram=1.2, machine_rate_per_hour=40.0)
    order = Order(pricing_mode="order_level", quantity=3, final_price=1500.0, plates=[p1, p2])
    rows = calc.plate_attributions(order, SETTINGS)
    for r in rows:
        assert r["profit"] == pytest.approx(r["revenue"] - r["cogs"])


def test_row_profit_equals_revenue_minus_cogs_per_plate_qty_gt_one_with_failures():
    p1 = plate(material_type="PLA", final_price=200.0,
               failed_attempts=[FailedAttempt(completion_percent=20.0)])
    p2 = plate(material_type="PETG", material_rate_per_gram=1.2,
               machine_rate_per_hour=40.0, final_price=120.0)
    order = Order(pricing_mode="per_plate", quantity=3, plates=[p1, p2])
    rows = calc.plate_attributions(order, SETTINGS)
    for r in rows:
        assert r["profit"] == pytest.approx(r["revenue"] - r["cogs"])


# -- only the failing plate should carry the extra cost -----------------------
def test_only_failing_plate_carries_extra_cost_order_level():
    p_failed = plate(material_type="PLA", failed_attempts=[FailedAttempt(completion_percent=30.0)])
    p_ok = plate(material_type="PETG")
    order = Order(pricing_mode="order_level", quantity=2, final_price=1000.0,
                  plates=[p_failed, p_ok])
    order_no_fail = Order(pricing_mode="order_level", quantity=2, final_price=1000.0,
                           plates=[plate(material_type="PLA"), plate(material_type="PETG")])

    rows = calc.plate_attributions(order, SETTINGS)
    rows_no_fail = calc.plate_attributions(order_no_fail, SETTINGS)

    # Revenue share is unchanged by the failure (identical base COGS -> 50/50
    # either way).
    assert rows[0]["revenue"] == pytest.approx(rows_no_fail[0]["revenue"])
    assert rows[1]["revenue"] == pytest.approx(rows_no_fail[1]["revenue"])

    # The failing plate alone absorbs the extra cost; the healthy plate's cogs
    # is untouched.
    failed_extra = calc.plate_failed_cost(p_failed)
    assert rows[0]["cogs"] == pytest.approx(rows_no_fail[0]["cogs"] + failed_extra)
    assert rows[1]["cogs"] == pytest.approx(rows_no_fail[1]["cogs"])

    assert sum(r["cogs"] for r in rows) == pytest.approx(calc.total_cogs_for_order(order))
    assert sum(r["revenue"] for r in rows) == pytest.approx(calc.order_final_price(order, SETTINGS))
    assert sum(r["profit"] for r in rows) == pytest.approx(calc.order_profit(order, SETTINGS))


# -- clone_for_calculator must never carry failed attempts forward -----------
def test_clone_for_calculator_drops_failed_attempts():
    p = plate(failed_attempts=[FailedAttempt(completion_percent=50.0)])
    clone = p.clone_for_calculator()
    assert clone.failed_attempts == []


# -- order_rollup new keys -----------------------------------------------------
def test_order_rollup_exposes_failed_cost_keys():
    p = plate(failed_attempts=[FailedAttempt(completion_percent=20.0)])
    order = Order(pricing_mode="order_level", plates=[p], quantity=3, final_price=1000.0)
    r = calc.order_rollup(order, SETTINGS)
    assert r["cogs_per_unit_delivered"] == pytest.approx(120.0)  # per-unit, delivered-only
    assert r["total_failed_cost"] == pytest.approx(24.0)
    assert r["total_cogs_for_order"] == pytest.approx(384.0)
    assert r["total_failed_material_cost"] == pytest.approx(18.0)
    assert r["total_failed_machine_cost"] == pytest.approx(6.0)


# -- the "total_cogs" naming trap: renamed keys, old ones gone for good -------
def test_order_rollup_no_longer_emits_old_key_names():
    p = plate(failed_attempts=[FailedAttempt(completion_percent=20.0)])
    order = Order(pricing_mode="order_level", plates=[p], quantity=3, final_price=1000.0)
    r = calc.order_rollup(order, SETTINGS)
    # A stale reader must KeyError, not silently read the wrong figure.
    assert "total_cogs" not in r
    assert "total_material_cost" not in r
    assert "total_machine_cost" not in r
    with pytest.raises(KeyError):
        r["total_cogs"]


def test_cogs_per_unit_delivered_excludes_failures_and_ignores_quantity():
    p = plate(failed_attempts=[FailedAttempt(completion_percent=20.0)])  # base cogs 120
    order = Order(pricing_mode="order_level", plates=[p], quantity=5, final_price=1000.0)
    r = calc.order_rollup(order, SETTINGS)
    # Neither the x5 quantity nor the failed attempt's cost shows up here.
    assert r["cogs_per_unit_delivered"] == pytest.approx(120.0)
    assert r["material_cost_per_unit"] == pytest.approx(90.0)
    assert r["machine_cost_per_unit"] == pytest.approx(30.0)


def test_total_cogs_for_order_includes_failures_and_scales_delivered_cogs():
    p = plate(failed_attempts=[FailedAttempt(completion_percent=20.0)])  # base cogs 120
    order = Order(pricing_mode="order_level", plates=[p], quantity=5, final_price=1000.0)
    r = calc.order_rollup(order, SETTINGS)
    # delivered cogs scaled by qty (120*5=600) + failed cost once (24, unscaled)
    assert r["total_cogs_for_order"] == pytest.approx(624.0)
