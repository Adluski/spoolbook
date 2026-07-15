# Spoolbook

A small desktop app for costing and tracking 3D‑print jobs — built for a
working Bambu A1 + AMS print business, not a demo. Enter an order as one or
more plates (different material per plate), let it compute COGS and a suggested
price, and keep a searchable history with a revenue/profit dashboard.

Python + PySide6 (native GUI) + SQLite (one local file, no server).

---

## What it does

- **Scratch calculator** — cost a job live (multiple plates, per‑plate
  material) with no customer name and nothing saved. One click converts it to a
  real order, prefilled.
- **Orders with multiple plates** — add/remove plate rows freely; each plate has
  its own material (PLA/PETG), source (own vs customer‑supplied), weight, print
  time and **rate snapshot**. Backdate the date/time, add notes, quantity and a
  bulk discount.
- **Two pricing modes per order** — *order‑level* (one final price + profit for
  the order, both manual overrides that default to the suggested numbers) or
  *per‑plate* (price/profit set on each plate). The toggle visibly changes which
  fields are editable.
- **Reprints** — log a reprint from any existing plate; it becomes a new plate
  on the same order (linked to the original) capturing just the extra
  weight/time.
- **History** — every order as an expandable row over its plates; filter by
  customer, date range, material or reprint status; sort any column.
- **Dashboard** — revenue, profit, COGS, margin and order count for a date
  range, broken down by material type.
- **CSV export** — one row per plate, with the order‑level fields duplicated on
  each row so nothing is lost.
- **Settings** — edit the default rates/markup/buffer. Changes apply to **new
  entries only**; historical plates keep the rate they were saved with.

## Costing

```
plate material cost = 0 if customer‑supplied, else weight_g × material_rate_per_g
plate machine cost  = (print_time_min / 60) × machine_rate_per_hour
plate COGS          = material cost + machine cost
order COGS          = Σ plate COGS
suggested price     = (COGS + buffer% × material cost) × markup   (× quantity, − bulk discount)
```

Every plate stores a **snapshot** of the rates that applied when it was
entered, so editing settings later never changes past jobs.

---

## Requirements

- Python **3.10+** (developed on 3.12)
- A desktop environment (it's a GUI app)

## Install & run

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python run.py
```

## Data location

The SQLite database lives at `~/.spoolbook/spoolbook.db` (created on first run).
It holds **real customer names, phone numbers and pricing**, so it is
`.gitignore`d and never committed. Point the app at a different file with the
`SPOOLBOOK_DB` environment variable — the test‑suite uses this to write to a
throwaway temp file.

## Tests

Calculation and database logic are covered by unit tests:

```bash
pytest
```

---

## Project layout

```
spoolbook/
  config.py           constants, default settings, db path
  models.py           Order / Plate data classes
  database.py         SQLite schema + CRUD + settings persistence
  calculations.py     pure costing / roll‑up / attribution logic
  csv_export.py       plate‑level CSV builder/writer
  app.py              QApplication entry point
  ui/
    theme.py          palette + global stylesheet
    widgets.py        shared widgets + value formatters
    main_window.py    nav rail + stacked screens
    plate_editor.py   reusable multi‑plate editor
    calculator_view.py
    order_entry_view.py
    settings_view.py
    history_view.py
    dashboard_view.py
    reprint_dialog.py
tests/                calculation, database and CSV tests
run.py                launcher (python run.py)
```

