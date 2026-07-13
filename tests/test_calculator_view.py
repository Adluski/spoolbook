"""Calculator-specific coverage: the scratch calculator must never show or
use the FAILURES column — a scratch estimate can't have failed a print it
hasn't run yet (see Plate.clone_for_calculator's docstring)."""
from __future__ import annotations

from spoolbook.config import DEFAULT_SETTINGS
from spoolbook.database import Database
from spoolbook.ui.calculator_view import CalculatorView
from spoolbook.ui.plate_editor import PlateRowsEditor


def test_calculator_plate_editor_hides_failures_column(qtbot, tmp_path):
    db = Database(tmp_path / "test.db")
    view = CalculatorView(db)
    qtbot.addWidget(view)
    assert view.plate_editor.allow_failures is False
    # isHidden() reflects the widget's own explicit visibility flag
    # regardless of whether the top-level window has been shown — exactly
    # what setVisible(allow_failures) sets, independent of qtbot.addWidget().
    assert view.plate_editor._h_failures.isHidden() is True
    row = view.plate_editor._rows[0]
    assert row.failures_btn.isHidden() is True
    db.close()


def test_plate_rows_editor_default_allows_failures():
    editor = PlateRowsEditor(dict(DEFAULT_SETTINGS))
    editor.add_plate()
    assert editor.allow_failures is True
    assert editor._h_failures.isHidden() is False
    assert editor._rows[0].failures_btn.isHidden() is False
