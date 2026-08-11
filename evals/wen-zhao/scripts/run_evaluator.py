#!/usr/bin/env python3
"""Compatibility entry point for the unified Wen Zhao evaluator."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUNNER = PROJECT_ROOT / "evals" / "scripts" / "run_evaluator.py"
PROFILE = PROJECT_ROOT / "evals" / "roles" / "wen-zhao.json"


if __name__ == "__main__":
    if not any(argument.startswith("--profile") for argument in sys.argv[1:]):
        sys.argv.extend(["--profile", str(PROFILE)])
    runpy.run_path(str(RUNNER), run_name="__main__")
