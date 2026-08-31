"""Score a run against ground truth. Fully deterministic — no LLM involved.

Usage:  python src/evaluate.py runs/<stage>

Nine scored fields per invoice:
  vendor_name, invoice_number, invoice_date, due_date, currency,
  subtotal, tax_amount, total, line_items
Strings are compared after normalization (case/punctuation-insensitive),
numbers within +/-0.01, line_items by item count + multiset of amounts.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GT_DIR = os.path.join(ROOT, "data", "ground_truth")

NUM_TOL = 0.01
FIELDS = ["vendor_name", "invoice_number", "invoice_date", "due_date",
          "currency", "subtotal", "tax_amount", "total", "line_items"]


def _norm_str(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _num_eq(a, b):
    return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) <= NUM_TOL


def field_correct(field, got, expected):
    if field in ("subtotal", "tax_amount", "total"):
        return _num_eq(got, expected)
    if field in ("vendor_name", "invoice_number"):
        return got is not None and _norm_str(got) == _norm_str(expected)
    if field in ("invoice_date", "due_date", "currency"):
        if expected is None:
            return got is None
        return isinstance(got, str) and got.strip().upper() == str(expected).upper() \
            if field == "currency" else got == expected
    if field == "line_items":
        if not isinstance(got, list) or len(got) != len(expected):
            return False
        got_amts = sorted(round(it.get("amount", float("nan")), 2)
                          for it in got if isinstance(it, dict))
        exp_amts = sorted(round(it["amount"], 2) for it in expected)
        if len(got_amts) != len(exp_amts):
            return False
        return all(abs(g - e) <= NUM_TOL for g, e in zip(got_amts, exp_amts))
    raise ValueError(field)


def evaluate_run(run_dir):
    per_invoice = {}
    for fname in sorted(os.listdir(GT_DIR)):
        if not fname.endswith(".json"):
            continue
        inv_id = fname[:-5]
        with open(os.path.join(GT_DIR, fname), encoding="utf-8") as f:
            expected = json.load(f)
        pred_path = os.path.join(run_dir, f"{inv_id}.json")
        predicted = {}
        if os.path.exists(pred_path):
            with open(pred_path, encoding="utf-8") as f:
                try:
                    predicted = json.load(f)
                except json.JSONDecodeError:
                    predicted = {}
        scores = {}
        for field in FIELDS:
            try:
                scores[field] = bool(field_correct(field, predicted.get(field), expected.get(field)))
            except Exception:
                scores[field] = False
        per_invoice[inv_id] = {
            "fields": scores,
            "correct": sum(scores.values()),
            "flagged_for_review": bool(predicted.get("needs_human_review")),
        }
    return per_invoice


def main():
    run_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "runs", "final")
    per_invoice = evaluate_run(run_dir)

    n_fields = len(FIELDS)
    total_fields = n_fields * len(per_invoice)
    total_correct = sum(v["correct"] for v in per_invoice.values())
    fully_correct = sum(1 for v in per_invoice.values() if v["correct"] == n_fields)
    flagged = sum(1 for v in per_invoice.values() if v["flagged_for_review"])

    meta = {}
    meta_path = os.path.join(run_dir, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

    print(f"\n=== {os.path.basename(run_dir)} ===")
    header = "invoice    " + "".join(f"{f[:9]:>10}" for f in FIELDS) + "   score"
    print(header)
    for inv_id, v in per_invoice.items():
        row = f"{inv_id:<11}" + "".join(f"{'OK' if v['fields'][f] else 'X':>10}" for f in FIELDS)
        flag = " [review]" if v["flagged_for_review"] else ""
        print(row + f"   {v['correct']}/{n_fields}{flag}")
    pct = 100.0 * total_correct / total_fields
    print(f"\nField accuracy:        {total_correct}/{total_fields}  ({pct:.1f}%)")
    print(f"Invoices fully correct: {fully_correct}/{len(per_invoice)}")
    print(f"Flagged for human review: {flagged}")
    if meta:
        print(f"LLM calls: {meta.get('llm_calls')}   wall time: {meta.get('wall_seconds')}s   "
              f"model: {meta.get('model')}")

    results = {
        "run": os.path.basename(run_dir),
        "field_accuracy_pct": round(pct, 1),
        "fields_correct": total_correct,
        "fields_total": total_fields,
        "invoices_fully_correct": fully_correct,
        "invoices": len(per_invoice),
        "flagged_for_review": flagged,
        "meta": meta,
        "per_invoice": per_invoice,
    }
    with open(os.path.join(run_dir, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {os.path.join(run_dir, 'results.json')}")


if __name__ == "__main__":
    main()
