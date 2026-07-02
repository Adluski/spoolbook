"""Colour system, fonts and the global Qt stylesheet.

Design intent: a dense, ledger-like workshop tool. Warm paper background,
near-black ink, a single burnt-filament orange accent, and a monospaced face
for every number so columns line up like an accounts book. Deliberately no
gradients, no drop shadows, no rounded "card" float — just flat fills and
hairline rules.
"""
from __future__ import annotations

# --- Palette ---------------------------------------------------------------
INK = "#241f18"          # primary text, near-black but warm
INK_SOFT = "#4c453a"     # secondary text
MUTED = "#8a8073"        # labels, hints, disabled
FAINT = "#b3ab9c"        # very low emphasis

PAPER = "#e9e4d8"        # window background
PANEL = "#faf8f2"        # panels / input surfaces
PANEL_ALT = "#f1ede2"    # zebra / header strips
SUNK = "#e2ddce"         # inset wells

LINE = "#d3ccbc"         # hairline borders
LINE_STRONG = "#bcb3a0"  # stronger dividers

ACCENT = "#c1541d"       # burnt filament orange — the one accent
ACCENT_DARK = "#9c4114"
ACCENT_PRESSED = "#833611"
ACCENT_TINT = "#f2e2d5"  # faint accent wash for selections

POSITIVE = "#2f7a54"     # profit / good
POSITIVE_TINT = "#e0ede4"
NEGATIVE = "#b23a2e"     # loss / destructive
WARNING = "#a9770f"      # advisory

# --- Fonts -----------------------------------------------------------------
UI_FONT_STACK = '"Segoe UI", "Inter", "Noto Sans", sans-serif'
MONO_FONT_STACK = '"Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace'
UI_FONT_FAMILY = "Segoe UI"
MONO_FONT_FAMILY = "Consolas"
BASE_POINT_SIZE = 10


def build_stylesheet() -> str:
    """Return the global QSS applied to the QApplication.

    Fully fleshed out in the styling pass; kept intentionally flat.
    """
    return f"""
    QWidget {{
        background: {PAPER};
        color: {INK};
        font-family: {UI_FONT_STACK};
        font-size: {BASE_POINT_SIZE}pt;
    }}
    QMainWindow, QDialog {{ background: {PAPER}; }}
    QToolTip {{
        background: {INK}; color: {PANEL};
        border: none; padding: 4px 7px;
    }}
    """
