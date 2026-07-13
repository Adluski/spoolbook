"""Regression test: mark_complete_dialog must not drop failed-attempt cost.

_live_cogs() rebuilds each plate via dataclasses.replace() with live
weight/duration but used to leave failed_attempts off the replacement, and
never added plate_failed_cost() back in — so a failure logged in the queue
silently vanished from the mark-complete dialog's COGS figure.
"""
from spoolbook import calculations as calc
from spoolbook.config import DEFAULT_SETTINGS
from spoolbook.models import FailedAttempt, Order, Plate
from spoolbook.ui.mark_complete_dialog import MarkCompleteDialog
from spoolbook.ui.widgets import fmt_money

SETTINGS = dict(DEFAULT_SETTINGS)


def make_order(**kw):
    plate = Plate(
        plate_label="Base", weight_grams=100.0, print_time_minutes=60,
        material_type="PLA", material_source="own",
        material_rate_per_gram=0.90, machine_rate_per_hour=25.0,
        failed_attempts=[FailedAttempt(completion_percent=20.0)],
    )
    base = dict(title="Job", customer_name="Rahul", pricing_mode="order_level",
                quantity=1, plates=[plate])
    base.update(kw)
    return Order(**base)


def test_live_cogs_includes_failed_attempt_cost(qtbot):
    order = make_order()
    dialog = MarkCompleteDialog(order, SETTINGS)
    qtbot.addWidget(dialog)

    total, per = dialog._live_cogs()

    plate = order.plates[0]
    expected = calc.plate_cogs(plate) + calc.plate_failed_cost(plate)
    assert total == expected
    assert per[0] == expected
    # Without the fix this would only be plate_cogs(plate) == 115.0, silently
    # dropping the 23.0 of wasted cost from the 20% failed attempt.
    assert total != calc.plate_cogs(plate)


def test_mark_complete_summary_reflects_failed_cost(qtbot):
    order = make_order()
    dialog = MarkCompleteDialog(order, SETTINGS)
    qtbot.addWidget(dialog)

    cogs_per_run, _ = dialog._live_cogs()
    plate = order.plates[0]
    assert cogs_per_run == calc.plate_cogs(plate) + calc.plate_failed_cost(plate)
    assert dialog.summary.text().startswith(f"COGS {fmt_money(cogs_per_run)}")
