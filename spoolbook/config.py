"""Application-wide constants, default settings and the on-disk database path.

Nothing here talks to Qt or SQLite; it is safe to import from any layer.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Spoolbook"
APP_TAGLINE = "3D print job costing & orders"

# Indian Rupee — this is an INR business.
CURRENCY = "₹"

# --- Enumerations used across the data model -------------------------------
MATERIALS = ("PLA", "PETG")

MATERIAL_SOURCES = ("own", "customer")
MATERIAL_SOURCE_LABELS = {
    "own": "Own filament",
    "customer": "Customer supplied",
}

PRICING_MODES = ("order_level", "per_plate")
PRICING_MODE_LABELS = {
    "order_level": "Order-level price",
    "per_plate": "Per-plate price",
}

# An order is either a realized job (completed) or a planned one waiting in the
# print queue (queued). Only completed orders count towards dashboard totals.
ORDER_STATUSES = ("completed", "queued")
STATUS_COMPLETED = "completed"
STATUS_QUEUED = "queued"

# --- Default settings ------------------------------------------------------
# These seed the settings table on first run and back the "restore defaults"
# action. Editing settings in-app NEVER rewrites historical plates: every
# plate stores its own snapshot of the rates that applied when it was entered.
DEFAULT_SETTINGS: dict[str, float] = {
    "pla_rate_per_gram": 0.90,
    "petg_rate_per_gram": 1.20,
    "pla_machine_rate_per_hour": 30.0,
    "petg_machine_rate_per_hour": 40.0,
    "markup_multiplier": 1.75,
    "pellet_buffer_percent": 5.0,
}


def material_rate_key(material_type: str) -> str:
    return f"{material_type.lower()}_rate_per_gram"


def machine_rate_key(material_type: str) -> str:
    return f"{material_type.lower()}_machine_rate_per_hour"


def db_path() -> Path:
    """Location of the SQLite file.

    Defaults to ``~/.spoolbook/spoolbook.db`` so the data survives moving or
    re-cloning the source tree. Override with the ``SPOOLBOOK_DB`` env var
    (used by the test-suite, which points it at a throwaway temp file).
    """
    override = os.environ.get("SPOOLBOOK_DB")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".spoolbook" / "spoolbook.db"
