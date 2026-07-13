"""Test-wide setup.

Must set QT_QPA_PLATFORM before any test module imports PySide6, so `pytest`
alone works headlessly with no env setup from the caller.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
