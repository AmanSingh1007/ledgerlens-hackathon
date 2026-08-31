"""Sanity-check the evaluation set: every ground-truth file must itself pass
the deterministic validator (so validator errors on model output always mean
the MODEL is wrong, never the data)."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validator import validate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GT_DIR = os.path.join(ROOT, "data", "ground_truth")

failures = 0
for fname in sorted(os.listdir(GT_DIR)):
    if not fname.endswith(".json"):
        continue
    with open(os.path.join(GT_DIR, fname), encoding="utf-8") as f:
        gt = json.load(f)
    errors = validate(gt)
    if errors:
        failures += 1
        print(f"FAIL {fname}")
        for e in errors:
            print(f"     - {e}")
    else:
        print(f"OK   {fname}")

if failures:
    print(f"\n{failures} ground-truth file(s) are internally inconsistent.")
    sys.exit(1)
print("\nAll ground-truth files pass the validator.")
