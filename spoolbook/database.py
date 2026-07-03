"""SQLite persistence for orders, plates and settings.

Single-file, single-connection, foreign keys on. All datetimes are stored as
``YYYY-MM-DD HH:MM:SS`` strings, which sort chronologically as plain text so
date-range filters are simple string comparisons.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .config import DEFAULT_SETTINGS
from .models import Order, Plate

DT_FMT = "%Y-%m-%d %H:%M:%S"

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    title                 TEXT    NOT NULL DEFAULT '',
    customer_name         TEXT    NOT NULL DEFAULT '',
    date_time             TEXT    NOT NULL,
    notes                 TEXT    NOT NULL DEFAULT '',
    pricing_mode          TEXT    NOT NULL DEFAULT 'order_level',
    status                TEXT    NOT NULL DEFAULT 'completed',
    final_price           REAL,
    profit                REAL,
    quantity              INTEGER NOT NULL DEFAULT 1,
    bulk_discount_percent REAL    NOT NULL DEFAULT 0,
    is_scratch            INTEGER NOT NULL DEFAULT 0,
    created_at            TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS plates (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id               INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    plate_label            TEXT    NOT NULL DEFAULT '',
    weight_grams           REAL    NOT NULL DEFAULT 0,
    print_time_minutes     INTEGER NOT NULL DEFAULT 0,
    material_type          TEXT    NOT NULL DEFAULT 'PLA',
    material_source        TEXT    NOT NULL DEFAULT 'own',
    material_rate_per_gram REAL    NOT NULL DEFAULT 0,
    machine_rate_per_hour  REAL    NOT NULL DEFAULT 0,
    final_price            REAL,
    profit                 REAL,
    is_reprint             INTEGER NOT NULL DEFAULT 0,
    linked_plate_id        INTEGER REFERENCES plates(id) ON DELETE SET NULL,
    position               INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_plates_order    ON plates(order_id);
CREATE INDEX IF NOT EXISTS idx_orders_datetime ON orders(date_time);
"""


def dt_to_str(dt: datetime) -> str:
    return dt.strftime(DT_FMT)


def str_to_dt(s: str) -> datetime:
    # Tolerate a stray fractional part if one ever slips in.
    return datetime.strptime(s.split(".")[0], DT_FMT)


class Database:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self._migrate()
        self._seed_settings()

    def close(self) -> None:
        self.conn.close()

    # -- migrations ---------------------------------------------------------
    def _migrate(self) -> None:
        """Additive migrations for databases created by earlier versions.

        The schema above uses ``CREATE TABLE IF NOT EXISTS``, so a table made by
        an older build is never altered by it. Bring such tables up to date by
        adding any columns they are missing (defaults keep old rows valid).
        """
        cols = {row["name"] for row in self.conn.execute("PRAGMA table_info(orders)")}
        with self.conn:
            if "status" not in cols:
                self.conn.execute(
                    "ALTER TABLE orders ADD COLUMN status TEXT NOT NULL "
                    "DEFAULT 'completed'"
                )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)"
            )

    # -- settings -----------------------------------------------------------
    def _seed_settings(self) -> None:
        with self.conn:
            for key, value in DEFAULT_SETTINGS.items():
                self.conn.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                    (key, str(value)),
                )

    def get_settings(self) -> dict[str, float]:
        """All settings as floats, defaults filling any gaps."""
        result = dict(DEFAULT_SETTINGS)
        for row in self.conn.execute("SELECT key, value FROM settings"):
            try:
                result[row["key"]] = float(row["value"])
            except (TypeError, ValueError):
                pass
        return result

    def get_setting(self, key: str) -> float:
        return self.get_settings()[key]

    def update_settings(self, values: dict[str, float]) -> None:
        with self.conn:
            for key, value in values.items():
                self.conn.execute(
                    "INSERT INTO settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value)),
                )

    # -- row <-> dataclass mapping -----------------------------------------
    @staticmethod
    def _row_to_order(row: sqlite3.Row) -> Order:
        return Order(
            id=row["id"],
            title=row["title"],
            customer_name=row["customer_name"],
            date_time=str_to_dt(row["date_time"]),
            notes=row["notes"],
            pricing_mode=row["pricing_mode"],
            status=row["status"],
            final_price=row["final_price"],
            profit=row["profit"],
            quantity=row["quantity"],
            bulk_discount_percent=row["bulk_discount_percent"],
            is_scratch=bool(row["is_scratch"]),
            created_at=str_to_dt(row["created_at"]),
        )

    @staticmethod
    def _row_to_plate(row: sqlite3.Row) -> Plate:
        return Plate(
            id=row["id"],
            order_id=row["order_id"],
            plate_label=row["plate_label"],
            weight_grams=row["weight_grams"],
            print_time_minutes=row["print_time_minutes"],
            material_type=row["material_type"],
            material_source=row["material_source"],
            material_rate_per_gram=row["material_rate_per_gram"],
            machine_rate_per_hour=row["machine_rate_per_hour"],
            final_price=row["final_price"],
            profit=row["profit"],
            is_reprint=bool(row["is_reprint"]),
            linked_plate_id=row["linked_plate_id"],
            position=row["position"],
        )

    # -- orders -------------------------------------------------------------
    def save_order(self, order: Order) -> int:
        """Insert or update an order and reconcile its plates in one transaction.

        Reconciliation preserves the ids of kept plates (so reprint links stay
        valid), inserts new rows, and deletes rows the user removed.
        """
        with self.conn:
            if order.id is None:
                order.id = self._insert_order(order)
            else:
                self._update_order(order)
            self._sync_plates(order)
        return order.id

    def _insert_order(self, order: Order) -> int:
        created = order.created_at or datetime.now()
        order.created_at = created
        cur = self.conn.execute(
            """INSERT INTO orders
               (title, customer_name, date_time, notes, pricing_mode, status,
                final_price, profit, quantity, bulk_discount_percent,
                is_scratch, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                order.title, order.customer_name, dt_to_str(order.date_time),
                order.notes, order.pricing_mode, order.status,
                order.final_price, order.profit,
                order.quantity, order.bulk_discount_percent,
                int(order.is_scratch), dt_to_str(created),
            ),
        )
        return cur.lastrowid

    def _update_order(self, order: Order) -> None:
        self.conn.execute(
            """UPDATE orders SET
                 title=?, customer_name=?, date_time=?, notes=?, pricing_mode=?,
                 status=?, final_price=?, profit=?, quantity=?,
                 bulk_discount_percent=?, is_scratch=?
               WHERE id=?""",
            (
                order.title, order.customer_name, dt_to_str(order.date_time),
                order.notes, order.pricing_mode, order.status,
                order.final_price, order.profit,
                order.quantity, order.bulk_discount_percent,
                int(order.is_scratch), order.id,
            ),
        )

    def _sync_plates(self, order: Order) -> None:
        existing = {
            row["id"]
            for row in self.conn.execute(
                "SELECT id FROM plates WHERE order_id=?", (order.id,)
            )
        }
        kept: set[int] = set()
        for position, plate in enumerate(order.plates):
            plate.order_id = order.id
            plate.position = position
            if plate.id is None or plate.id not in existing:
                plate.id = self._insert_plate(plate)
            else:
                self._update_plate(plate)
                kept.add(plate.id)
        for stale_id in existing - kept:
            self.conn.execute("DELETE FROM plates WHERE id=?", (stale_id,))

    def _insert_plate(self, plate: Plate) -> int:
        cur = self.conn.execute(
            """INSERT INTO plates
               (order_id, plate_label, weight_grams, print_time_minutes,
                material_type, material_source, material_rate_per_gram,
                machine_rate_per_hour, final_price, profit, is_reprint,
                linked_plate_id, position)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                plate.order_id, plate.plate_label, plate.weight_grams,
                plate.print_time_minutes, plate.material_type,
                plate.material_source, plate.material_rate_per_gram,
                plate.machine_rate_per_hour, plate.final_price, plate.profit,
                int(plate.is_reprint), plate.linked_plate_id, plate.position,
            ),
        )
        return cur.lastrowid

    def _update_plate(self, plate: Plate) -> None:
        self.conn.execute(
            """UPDATE plates SET
                 plate_label=?, weight_grams=?, print_time_minutes=?,
                 material_type=?, material_source=?, material_rate_per_gram=?,
                 machine_rate_per_hour=?, final_price=?, profit=?, is_reprint=?,
                 linked_plate_id=?, position=?
               WHERE id=?""",
            (
                plate.plate_label, plate.weight_grams, plate.print_time_minutes,
                plate.material_type, plate.material_source,
                plate.material_rate_per_gram, plate.machine_rate_per_hour,
                plate.final_price, plate.profit, int(plate.is_reprint),
                plate.linked_plate_id, plate.position, plate.id,
            ),
        )

    def add_plate(self, plate: Plate) -> int:
        """Insert a single plate (used by the reprint flow) and return its id."""
        with self.conn:
            plate.id = self._insert_plate(plate)
        return plate.id

    def get_order(self, order_id: int) -> Optional[Order]:
        row = self.conn.execute(
            "SELECT * FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        if row is None:
            return None
        order = self._row_to_order(row)
        order.plates = self._load_plates([order_id]).get(order_id, [])
        return order

    def get_plate(self, plate_id: int) -> Optional[Plate]:
        row = self.conn.execute(
            "SELECT * FROM plates WHERE id=?", (plate_id,)
        ).fetchone()
        return self._row_to_plate(row) if row else None

    def _load_plates(self, order_ids: Iterable[int]) -> dict[int, list[Plate]]:
        ids = list(order_ids)
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT * FROM plates WHERE order_id IN ({placeholders}) "
            f"ORDER BY position, id",
            ids,
        )
        grouped: dict[int, list[Plate]] = {oid: [] for oid in ids}
        for row in rows:
            grouped[row["order_id"]].append(self._row_to_plate(row))
        return grouped

    def list_orders(
        self,
        *,
        customer: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        material: Optional[str] = None,
        reprint_only: bool = False,
        include_scratch: bool = False,
        status: Optional[str] = None,
    ) -> list[Order]:
        clauses = []
        params: list = []
        if not include_scratch:
            clauses.append("is_scratch = 0")
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if customer:
            clauses.append("customer_name LIKE ?")
            params.append(f"%{customer}%")
        if start is not None:
            clauses.append("date_time >= ?")
            params.append(dt_to_str(start))
        if end is not None:
            clauses.append("date_time <= ?")
            params.append(dt_to_str(end))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM orders {where} ORDER BY date_time DESC, id DESC",
            params,
        ).fetchall()

        orders = [self._row_to_order(r) for r in rows]
        plates = self._load_plates([o.id for o in orders])
        for order in orders:
            order.plates = plates.get(order.id, [])

        # Plate-dependent filters are applied in Python.
        if material:
            orders = [
                o for o in orders
                if any(p.material_type == material for p in o.plates)
            ]
        if reprint_only:
            orders = [o for o in orders if any(p.is_reprint for p in o.plates)]
        return orders

    def delete_order(self, order_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM orders WHERE id=?", (order_id,))

    def delete_plate(self, plate_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM plates WHERE id=?", (plate_id,))
