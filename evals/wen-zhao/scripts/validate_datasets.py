#!/usr/bin/env python3
"""Compatibility entry point for the unified dataset validator."""

from __future__ import annotations

import runpy
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = PROJECT_ROOT / "evals" / "scripts" / "validate_datasets.py"
if __name__ == "__main__":
    runpy.run_path(str(VALIDATOR), run_name="__main__")
