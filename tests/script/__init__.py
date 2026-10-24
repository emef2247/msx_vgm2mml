"""Test scripts; also keep repository-root unittest discovery usable."""
from pathlib import Path
import sys

# Historical tests import their shared helpers as sibling modules.
_test_scripts = str(Path(__file__).resolve().parent)
if _test_scripts not in sys.path:
    sys.path.insert(0, _test_scripts)
