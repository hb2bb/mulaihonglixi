#!/usr/bin/env python3
"""Generate the second post-fix regression set from v4 human failures."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATASETS_DIR = ROOT.parent / "datasets"
v4 = {item["id"]: item for item in json.loads((DATASETS_DIR / "dialogue-targeted-regression-v4.json").read_text(encoding="utf-8"))}
selected = [
    "rv4-natural-05", "rv4-natural-07", "rv4-natural-09", "rv4-pause-06",
    "rv4-pause-09", "rv4-real-05", "rv4-real-07", "rv4-safe-01",
    "rv4-safe-02", "rv4-safe-04", "rv4-safe-08", "rv4-safe-09",
]
items = []
for index, old_id in enumerate(selected, 1):
    item = dict(v4[old_id])
    item["id"] = f"rv5-{index:02d}"
    item["regression_of"] = old_id
    items.append(item)

out = DATASETS_DIR / "dialogue-targeted-regression-v5.json"
out.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {len(items)} cases to {out}")
