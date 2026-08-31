"""Replay experiment: what would the validator + corrector have done with the
BASELINE's actual (observed, faulty) extractions?

For every baseline output: run the deterministic validator. If it reports
errors, run the correction loop exactly as the agent would, then re-score the
field(s) against ground truth. This isolates iteration 2's contribution on
real observed failures, independent of whether the engineered extraction
prompt happens to avoid those failures in a given run.

Usage: python src/replay_validator.py [runs/baseline]
Writes: runs/replay/replay_results.json (+ corrected extractions)
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evaluate import FIELDS, field_correct
from llm import complete, extract_json
from prompts import CORRECTION_PROMPT
from validator import validate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INV_DIR = os.path.join(ROOT, "data", "invoices")
GT_DIR = os.path.join(ROOT, "data", "ground_truth")
MAX_CORRECTIONS = 2


def main():
    src_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "runs", "baseline")
    out_dir = os.path.join(ROOT, "runs", "replay")
    os.makedirs(out_dir, exist_ok=True)

    report = []
    for fname in sorted(os.listdir(GT_DIR)):
        if not fname.endswith(".json"):
            continue
        inv_id = fname[:-5]
        with open(os.path.join(GT_DIR, fname), encoding="utf-8") as f:
            gt = json.load(f)
        with open(os.path.join(src_dir, f"{inv_id}.json"), encoding="utf-8") as f:
            extraction = json.load(f)
        with open(os.path.join(INV_DIR, f"{inv_id}.txt"), encoding="utf-8") as f:
            document = f.read()

        wrong_before = [fld for fld in FIELDS if not field_correct(fld, extraction.get(fld), gt.get(fld))]
        errors = validate(extraction)
        entry = {
            "invoice": inv_id,
            "wrong_fields_before": wrong_before,
            "validator_errors": errors,
            "detected": bool(errors),
        }

        if errors:
            result = extraction
            attempts = 0
            while errors and attempts < MAX_CORRECTIONS:
                attempts += 1
                reply = complete(CORRECTION_PROMPT.format(
                    document=document,
                    previous=json.dumps(result, indent=2),
                    errors="\n".join(f"- {e}" for e in errors),
                ))
                try:
                    result = extract_json(reply)
                except Exception:
                    continue
                errors = validate(result)
            wrong_after = [fld for fld in FIELDS if not field_correct(fld, result.get(fld), gt.get(fld))]
            entry["correction_attempts"] = attempts
            entry["wrong_fields_after"] = wrong_after
            entry["remaining_validator_errors"] = errors
            with open(os.path.join(out_dir, f"{inv_id}_corrected.json"), "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)

        report.append(entry)
        status = "clean" if not wrong_before else ("DETECTED" if entry["detected"] else "SILENT MISS")
        print(f"{inv_id}: wrong_before={wrong_before or '-'} -> {status}"
              + (f", wrong_after={entry.get('wrong_fields_after')}" if errors is not None and entry["detected"] else ""))

    faulty = [e for e in report if e["wrong_fields_before"]]
    detected = [e for e in faulty if e["detected"]]
    fixed = [e for e in detected if not e.get("wrong_fields_after")]
    print(f"\nFaulty baseline extractions: {len(faulty)}")
    print(f"Detected by validator:       {len(detected)}  ({[e['invoice'] for e in detected]})")
    print(f"Fully fixed by corrector:    {len(fixed)}  ({[e['invoice'] for e in fixed]})")
    print(f"Silent (validator-invisible): {[e['invoice'] for e in faulty if not e['detected']]}")

    with open(os.path.join(out_dir, "replay_results.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nWrote {os.path.join(out_dir, 'replay_results.json')}")


if __name__ == "__main__":
    main()
