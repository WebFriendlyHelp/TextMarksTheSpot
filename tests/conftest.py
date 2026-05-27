# Pytest configuration for Text Marks the Spot.
#
# The classifier and landing finders are pure-Python (no NVDA imports) by
# design — so we can exercise them in a plain Python environment without
# NVDA running. This conftest just adds the addon's plugin folder to the
# import path so tests can `import classifier` and `from detection import
# web` directly.

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "addon" / "globalPlugins" / "TextMarksTheSpot"
sys.path.insert(0, str(PLUGIN))
