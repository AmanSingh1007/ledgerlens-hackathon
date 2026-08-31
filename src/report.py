"""Aggregate all runs/<stage>/results.json into RESULTS.md."""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "runs")

ORDER = ["baseline", "context", "context_r2", "context_r3", "verify", "memory", "judge", "final"]
LABELS = {
    "baseline":   "Stage 0 — Baseline (one direct prompt)",
    "context":    "Iteration 1 — Engineered context",
    "context_r2": "Iteration 1 — repeat run 2 (variance)",
    "context_r3": "Iteration 1 — repeat run 3 (variance)",
    "verify":     "Iteration 2 — + Validator & correction loop",
    "memory":     "Iteration 3 — + Vendor memory",
    "judge":      "Iteration 4 — + LLM judge (removed)",
    "final":      "Final — context + validator + memory",
}


def main():
    rows = []
    for stage in ORDER:
        path = os.path.join(RUNS, stage, "results.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            r = json.load(f)
        rows.append(r)

    lines = [
        "# LedgerLens — Evaluation Results",
        "",
        f"Model: `{rows[-1]['meta'].get('model', '?')}` for every stage (same model, same 14 invoices — only the workflow changes).",
        "",
        "| Stage | Field accuracy | Fully correct invoices | Flagged for review | LLM calls | Wall time |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        stage = r["run"]
        lines.append(
            f"| {LABELS.get(stage, stage)} "
            f"| {r['fields_correct']}/{r['fields_total']} ({r['field_accuracy_pct']}%) "
            f"| {r['invoices_fully_correct']}/{r['invoices']} "
            f"| {r['flagged_for_review']} "
            f"| {r['meta'].get('llm_calls', '?')} "
            f"| {r['meta'].get('wall_seconds', '?')}s |"
        )

    lines += ["", "## Per-invoice field scores (final stage vs baseline)", ""]
    base = next((r for r in rows if r["run"] == "baseline"), None)
    final = next((r for r in rows if r["run"] == "final"), rows[-1])
    if base and final:
        lines.append("| Invoice | Baseline | Final |")
        lines.append("|---|---|---|")
        for inv in sorted(final["per_invoice"]):
            b = base["per_invoice"].get(inv, {}).get("correct", "?")
            fv = final["per_invoice"][inv]["correct"]
            lines.append(f"| {inv} | {b}/9 | {fv}/9 |")

    out = os.path.join(ROOT, "RESULTS.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
