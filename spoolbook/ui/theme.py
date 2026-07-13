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

CREAM = "#f4efe4"        # on-dark text
WHITE_TEXT = "#fdf7ee"   # text on the accent

# The left rail is a dark warm charcoal for a strong tool-like anchor.
RAIL_BG = "#2a241d"
RAIL_HOVER = "#332c24"
RAIL_ACTIVE = "#3b3228"
RAIL_TEXT = "#cec5b4"
RAIL_DIM = "#8d8474"

# --- Fonts -----------------------------------------------------------------
UI_FONT_STACK = '"Segoe UI", "Inter", "Noto Sans", sans-serif'
MONO_FONT_STACK = '"Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace'
UI_FONT_FAMILY = "Segoe UI"
MONO_FONT_FAMILY = "Consolas"
BASE_POINT_SIZE = 10


def build_stylesheet() -> str:
    """Return the global QSS applied to the QApplication.

    Strategy: default every widget to a transparent background and paint the
    real surfaces (window, rail, panels, bars, inputs) explicitly. That keeps
    labels from drawing opaque boxes over the surface behind them.
    """
    return f"""
    /* ---- base -------------------------------------------------------- */
    QWidget {{
        background: transparent;
        color: {INK};
        font-family: {UI_FONT_STACK};
        font-size: {BASE_POINT_SIZE}pt;
    }}
    #MainWindow, QDialog {{ background: {PAPER}; }}
    QLabel, QCheckBox, QRadioButton {{ background: transparent; }}

    /* ---- navigation rail --------------------------------------------- */
    #NavRail {{ background: {RAIL_BG}; }}
    #Wordmark {{
        color: {CREAM}; font-size: 15pt; font-weight: 700;
        letter-spacing: 0.5px;
    }}
    #Tagline {{ color: {RAIL_DIM}; font-size: 8.5pt; }}
    #NavButton {{
        background: transparent; color: {RAIL_TEXT};
        border: none; border-left: 3px solid transparent;
        text-align: left; padding: 9px 18px 9px 17px;
        font-size: 10.5pt;
    }}
    #NavButton:hover {{ background: {RAIL_HOVER}; color: {CREAM}; }}
    #NavButton:checked {{
        background: {RAIL_ACTIVE}; color: {CREAM};
        border-left: 3px solid {ACCENT}; font-weight: 600;
    }}
    #Version {{ color: {RAIL_DIM}; font-size: 8pt; }}

    /* ---- bars & surfaces --------------------------------------------- */
    #TopBar {{ background: {PAPER}; border-bottom: 1px solid {LINE}; }}
    #FilterBar {{
        background: {PANEL_ALT};
        border-top: 1px solid {LINE}; border-bottom: 1px solid {LINE};
    }}
    #SummaryBar {{ background: {PANEL_ALT}; border-top: 1px solid {LINE_STRONG}; }}
    #Panel {{
        background: {PANEL}; border: 1px solid {LINE}; border-radius: 4px;
    }}
    #HLine {{ background: {LINE}; border: none; max-height: 1px; }}

    /* ---- typography -------------------------------------------------- */
    #PageTitle {{ font-size: 17pt; font-weight: 700; color: {INK}; }}
    #PageSubtitle {{ font-size: 10pt; color: {MUTED}; }}
    #SectionLabel {{
        color: {MUTED}; font-size: 8.5pt; font-weight: 700;
        letter-spacing: 1px;
    }}
    #FieldLabel {{ color: {INK_SOFT}; font-size: 9.5pt; }}
    #Muted {{ color: {MUTED}; font-size: 9.5pt; }}
    #UnitLabel {{ color: {MUTED}; font-size: 9pt; }}
    #FormulaHint {{ color: {MUTED}; font-size: 9pt; font-style: italic; }}
    #ColHead {{
        color: {MUTED}; font-size: 8.5pt; font-weight: 700; letter-spacing: 0.5px;
    }}
    #DialogNote {{ color: {INK_SOFT}; font-size: 10pt; }}
    #StatusOk {{ color: {POSITIVE}; font-size: 9pt; }}
    #StatusError {{ color: {NEGATIVE}; font-size: 9pt; font-weight: 600; }}

    #Notice {{
        background: {ACCENT_TINT}; color: {ACCENT_DARK};
        border: 1px solid #e6c8ad; border-left: 3px solid {ACCENT};
        border-radius: 4px; padding: 10px 13px; font-size: 9.5pt;
    }}

    /* ---- inputs ------------------------------------------------------ */
    QLineEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox,
    QDateTimeEdit, QDateEdit {{
        background: {PANEL}; color: {INK};
        border: 1px solid {LINE_STRONG}; border-radius: 3px;
        padding: 4px 7px; selection-background-color: {ACCENT};
        selection-color: {WHITE_TEXT};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
    QAbstractSpinBox:focus, QDateTimeEdit:focus, QDateEdit:focus {{
        border: 1px solid {ACCENT};
    }}
    QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled,
    QDateEdit:disabled {{ color: {FAINT}; background: {SUNK}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox::down-arrow {{
        image: none; border-left: 4px solid transparent;
        border-right: 4px solid transparent; border-top: 5px solid {MUTED};
        margin-right: 6px;
    }}
    QComboBox QAbstractItemView {{
        background: {PANEL}; border: 1px solid {LINE_STRONG};
        selection-background-color: {ACCENT_TINT}; selection-color: {INK};
        outline: none;
    }}

    /* ---- buttons ----------------------------------------------------- */
    QPushButton {{
        background: {PANEL}; color: {INK};
        border: 1px solid {LINE_STRONG}; border-radius: 3px;
        padding: 6px 12px;
    }}
    QPushButton:hover {{ background: {PANEL_ALT}; }}
    #PrimaryButton {{
        background: {ACCENT}; color: {WHITE_TEXT}; font-weight: 600;
        border: 1px solid {ACCENT_DARK}; border-radius: 3px; padding: 7px 18px;
    }}
    #PrimaryButton:hover {{ background: {ACCENT_DARK}; }}
    #PrimaryButton:pressed {{ background: {ACCENT_PRESSED}; }}
    #SecondaryButton {{
        background: transparent; color: {INK_SOFT};
        border: 1px solid {LINE_STRONG}; border-radius: 3px; padding: 6px 14px;
    }}
    #SecondaryButton:hover {{ background: {PANEL_ALT}; color: {INK}; }}
    #DangerButton {{
        background: transparent; color: {NEGATIVE};
        border: 1px solid {NEGATIVE}; border-radius: 3px; padding: 6px 14px;
    }}
    #DangerButton:hover {{ background: {NEGATIVE}; color: {WHITE_TEXT}; }}
    #DangerButton:disabled {{
        color: {MUTED}; border-color: {LINE_STRONG}; background: transparent;
    }}
    #AddPlateButton {{
        background: transparent; color: {ACCENT}; font-weight: 600;
        border: none; padding: 6px 4px; text-align: left;
    }}
    #AddPlateButton:hover {{ color: {ACCENT_DARK}; }}
    #RowRemove {{
        background: transparent; color: {MUTED}; border: none;
        font-size: 12pt; padding: 0;
    }}
    #RowRemove:hover {{ color: {NEGATIVE}; }}
    #ResetButton {{
        background: transparent; color: {MUTED}; border: 1px solid {LINE};
        border-radius: 3px; padding: 2px 6px; font-size: 11pt;
    }}
    #ResetButton:hover {{ color: {ACCENT}; border-color: {ACCENT}; }}

    /* ---- segmented control ------------------------------------------- */
    #SegItem {{
        background: {PANEL}; color: {INK_SOFT};
        border: 1px solid {LINE_STRONG}; border-radius: 0; padding: 5px 15px;
    }}
    #SegItem:hover {{ background: {PANEL_ALT}; }}
    #SegItem:checked {{
        background: {ACCENT}; color: {WHITE_TEXT};
        border: 1px solid {ACCENT_DARK};
    }}

    /* ---- stat chips & metrics ---------------------------------------- */
    #StatChip {{
        background: {PANEL}; border: 1px solid {LINE}; border-radius: 4px;
    }}
    #StatCaption {{
        color: {MUTED}; font-size: 8pt; font-weight: 700; letter-spacing: 0.8px;
    }}
    #StatValue {{
        color: {INK}; font-family: {MONO_FONT_STACK};
        font-size: 12pt; font-weight: 700;
    }}
    #StatValueStrong {{
        color: {INK}; font-family: {MONO_FONT_STACK};
        font-size: 13pt; font-weight: 700;
    }}
    #MarginValue {{
        color: {INK}; font-family: {MONO_FONT_STACK};
        font-size: 12pt; font-weight: 700;
    }}
    #MetricValue {{
        color: {INK}; font-family: {MONO_FONT_STACK};
        font-size: 20pt; font-weight: 700;
    }}
    #MetricValueAccent {{
        color: {ACCENT}; font-family: {MONO_FONT_STACK};
        font-size: 20pt; font-weight: 700;
    }}
    *[tone="positive"] {{ color: {POSITIVE}; }}
    *[tone="negative"] {{ color: {NEGATIVE}; }}
    *[tone="accent"]   {{ color: {ACCENT}; }}

    /* ---- plate editor rows ------------------------------------------- */
    #PlateHeader {{ background: {PANEL_ALT}; border-bottom: 1px solid {LINE}; }}
    #PlateRow {{ background: {PANEL}; border-bottom: 1px solid #ece7db; }}
    #RowCogs {{ font-family: {MONO_FONT_STACK}; font-weight: 700; color: {INK}; }}
    #ReprintBadge {{ color: {ACCENT}; font-weight: 700; }}
    #FailuresButton {{
        background: {PANEL_ALT}; color: {INK_SOFT}; border: 1px solid {LINE};
        border-radius: 3px; font-weight: 700; padding: 2px 0;
    }}
    #FailuresButton:hover {{ color: {ACCENT}; border-color: {ACCENT}; }}

    /* ---- tree / table ------------------------------------------------ */
    #HistoryTree, #MaterialTable {{
        background: {PANEL}; alternate-background-color: {PANEL_ALT};
        border: 1px solid {LINE}; border-radius: 4px;
        gridline-color: {LINE};
    }}
    QTreeWidget::item, QTableWidget::item {{
        padding: 5px 6px; border: none;
    }}
    QTreeWidget::item:selected, QTableWidget::item:selected {{
        background: {ACCENT_TINT}; color: {INK};
    }}
    QHeaderView::section {{
        background: {PANEL_ALT}; color: {MUTED};
        padding: 6px 8px; border: none;
        border-bottom: 1px solid {LINE_STRONG}; border-right: 1px solid {LINE};
        font-size: 8.5pt; font-weight: 700;
    }}
    QTreeWidget::branch {{ background: transparent; }}

    /* ---- scrollbars -------------------------------------------------- */
    QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
    QScrollBar::handle:vertical {{
        background: {LINE_STRONG}; border-radius: 5px; min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
    QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
    QScrollBar::handle:horizontal {{
        background: {LINE_STRONG}; border-radius: 5px; min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {MUTED}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* ---- checkboxes -------------------------------------------------- */
    QCheckBox {{ color: {INK_SOFT}; spacing: 6px; }}
    QCheckBox::indicator {{
        width: 15px; height: 15px; border: 1px solid {LINE_STRONG};
        border-radius: 3px; background: {PANEL};
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT}; border: 1px solid {ACCENT_DARK};
    }}

    /* ---- menus & calendar -------------------------------------------- */
    QMenu {{ background: {PANEL}; border: 1px solid {LINE_STRONG}; padding: 4px; }}
    QMenu::item {{ padding: 6px 20px; border-radius: 3px; }}
    QMenu::item:selected {{ background: {ACCENT_TINT}; color: {INK}; }}
    QMenu::separator {{ height: 1px; background: {LINE}; margin: 4px 6px; }}
    QCalendarWidget QAbstractItemView {{
        selection-background-color: {ACCENT}; selection-color: {WHITE_TEXT};
    }}
    QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {PANEL_ALT}; }}

    /* ---- tooltip ----------------------------------------------------- */
    QToolTip {{
        background: {INK}; color: {CREAM};
        border: none; padding: 5px 8px; font-size: 9pt;
    }}
    """
