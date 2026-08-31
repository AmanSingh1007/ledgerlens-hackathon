# LedgerLens — Evaluation Results

Model: `claude-haiku-4-5-20251001` for every stage (same model, same 14 invoices — only the workflow changes).

| Stage | Field accuracy | Fully correct invoices | Flagged for review | LLM calls | Wall time |
|---|---|---|---|---|---|
| Stage 0 — Baseline (one direct prompt) | 120/126 (95.2%) | 9/14 | 0 | 14 | 233.8s |
| Iteration 1 — Engineered context | 123/126 (97.6%) | 12/14 | 0 | 14 | 313.1s |
| Iteration 1 — repeat run 2 (variance) | 123/126 (97.6%) | 12/14 | 0 | 14 | 300.0s |
| Iteration 1 — repeat run 3 (variance) | 124/126 (98.4%) | 13/14 | 0 | 14 | 319.6s |
| Iteration 2 — + Validator & correction loop | 123/126 (97.6%) | 12/14 | 0 | 14 | 270.6s |
| Iteration 3 — + Vendor memory | 126/126 (100.0%) | 14/14 | 0 | 15 | 334.4s |
| Iteration 4 — + LLM judge (removed) | 125/126 (99.2%) | 13/14 | 0 | 29 | 629.1s |
| Final — context + validator + memory | 126/126 (100.0%) | 14/14 | 0 | 14 | 719.6s |

## Per-invoice field scores (final stage vs baseline)

| Invoice | Baseline | Final |
|---|---|---|
| inv_01 | 9/9 | 9/9 |
| inv_02 | 9/9 | 9/9 |
| inv_03 | 8/9 | 9/9 |
| inv_04 | 9/9 | 9/9 |
| inv_05 | 9/9 | 9/9 |
| inv_06 | 9/9 | 9/9 |
| inv_07 | 7/9 | 9/9 |
| inv_08 | 8/9 | 9/9 |
| inv_09 | 9/9 | 9/9 |
| inv_10 | 9/9 | 9/9 |
| inv_11 | 8/9 | 9/9 |
| inv_12 | 9/9 | 9/9 |
| inv_13 | 9/9 | 9/9 |
| inv_14 | 8/9 | 9/9 |
