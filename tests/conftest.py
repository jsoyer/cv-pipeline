"""Pytest configuration: ensure scripts/ is importable."""

import sys
from pathlib import Path

# Add scripts/ to sys.path so that `from lib.common import ...` works.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
