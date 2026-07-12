"""Plain data classes for the two records the app revolves around.

These are deliberately dumb containers — no persistence, no Qt. The database
layer maps rows to/from these, and the calculation layer reads them. Every
rate a plate needs is stored *on the plate* as a snapshot, so historical
records never shift when settings change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Plate:
    id: Optional[int] = None
    order_id: Optional[int] = None
    plate_label: str = ""
    weight_grams: float = 0.0
    print_time_minutes: int = 0
    material_type: str = "PLA"          # PLA | PETG
    material_source: str = "own"        # own | customer  (customer supplied = no material cost)
    # Rate snapshots — captured when the plate is entered, never re-read live.
    material_rate_per_gram: float = 0.0
    machine_rate_per_hour: float = 0.0
    # Used only when the parent order is in per_plate pricing mode.
    # final_price is the one input; profit is always derived as
    # final_price − COGS (calculations.per_plate_profit) and is stored here
    # only as a persisted snapshot — nothing reads it back as truth.
    final_price: Optional[float] = None
    profit: Optional[float] = None
    # Reprint linkage.
    is_reprint: bool = False
    linked_plate_id: Optional[int] = None
    position: int = 0

    def clone_for_calculator(self) -> "Plate":
        """A detached copy with no identity, for prefilling the entry screen."""
        return Plate(
            plate_label=self.plate_label,
            weight_grams=self.weight_grams,
            print_time_minutes=self.print_time_minutes,
            material_type=self.material_type,
            material_source=self.material_source,
            material_rate_per_gram=self.material_rate_per_gram,
            machine_rate_per_hour=self.machine_rate_per_hour,
        )


@dataclass
class Order:
    id: Optional[int] = None
    title: str = ""
    customer_name: str = ""
    date_time: datetime = field(default_factory=datetime.now)
    notes: str = ""
    pricing_mode: str = "order_level"   # order_level | per_plate
    # queued  = a planned print not yet done (shown in the Queue, excluded from
    #           dashboard totals). completed = a realized order.
    status: str = "completed"           # completed | queued
    # Used only in order_level mode. final_price is a manual override (defaults
    # to the suggested price). profit is always derived as final_price − COGS;
    # the stored value is only a snapshot and is never trusted over that
    # subtraction (see calculations.resolved_order_level_profit).
    final_price: Optional[float] = None
    profit: Optional[float] = None
    quantity: int = 1
    bulk_discount_percent: float = 0.0
    is_scratch: bool = False
    created_at: Optional[datetime] = None
    plates: list[Plate] = field(default_factory=list)
