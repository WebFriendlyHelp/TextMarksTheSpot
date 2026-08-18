# Pytest configuration for Text Marks the Spot.
#
# The classifier and landing finders are pure-Python (no NVDA imports) by
# design — so we can exercise them in a plain Python environment without
# NVDA running. This conftest just adds the addon's plugin folder to the
# import path so tests can `import classifier` and `from detection import
# web` directly.

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "addon" / "globalPlugins" / "TextMarksTheSpot"
sys.path.insert(0, str(PLUGIN))


# ---------------------------------------------------------------------------
# THE TEST SUITE MUST NEVER SEE THE REAL APPDATA. Set at import time, before a
# single test or even a module-level `import tree_summary` can run.
#
# This is not hygiene, it is a defect that already happened (2026-08-18). The
# diagnostic logs are gated on a marker file under %APPDATA%\nvda, and the
# moment that marker exists on a developer's machine -- which is the whole
# point of it, and the state any real debugging session is in -- the suite
# starts writing into the user's OWN logs. `_log_landmark_probe` calls
# `_append_perf_line`, and tests in test_chrome_scope.py and test_walk_wiring.py
# drive the landmark scan directly, so one `sabotage_check.py` run (30-odd full
# suite passes) put 1022 synthetic probe lines into a real perf log that held 4
# real ones.
#
# Two things that costs, and the second is the serious one:
#   1. The signal is buried 250:1 in fixture noise.
#   2. The perf log SELF-ROTATES at 1 MB, keeping one generation. Enough test
#      runs silently destroy the real browsing data the log was turned on to
#      collect -- and it looks like nothing went wrong.
#
# Pointing APPDATA at an empty temp directory makes `_diagnostics_enabled()`
# answer False for the whole run, because no marker lives there. Tests that
# exercise the gate itself (test_diagnostic_optin.py) monkeypatch APPDATA
# per-test and still win, since function-scoped monkeypatch applies after this.
_TEST_APPDATA = Path(tempfile.gettempdir()) / "tmts-test-appdata"
_TEST_APPDATA.mkdir(parents=True, exist_ok=True)
os.environ["APPDATA"] = str(_TEST_APPDATA)
