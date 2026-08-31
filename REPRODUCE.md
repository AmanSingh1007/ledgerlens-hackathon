# Reproduction Guide

This guide assumes a **clean environment**. Total setup time ≈ 5 minutes; full
evaluation run ≈ 15–35 minutes depending on the engine and model latency.

## 1. Prerequisites

| Requirement | Version used | Notes |
|---|---|---|
| Python | 3.11 (any ≥ 3.9 works) | Standard library only — **no pip installs** |
| An LLM engine | see below | one of the two options |

**Engine option A — Claude Code CLI (what we used, no API key needed):**
Install [Claude Code](https://claude.com/claude-code) (we used v2.1.251) and log in
(`claude` once, follow the prompt). LedgerLens shells out to `claude -p`.

**Engine option B — Anthropic API key:**
```
set ANTHROPIC_API_KEY=sk-ant-...        (Windows cmd)
export ANTHROPIC_API_KEY=sk-ant-...     (bash)
```
No SDK install needed — the project calls the HTTPS API with the standard library.

The engine is picked automatically (`api` if `ANTHROPIC_API_KEY` is set, else `cli`).
Override with `LEDGERLENS_ENGINE=cli|api`. The model is pinned to
`claude-haiku-4-5-20251001` for both baseline and agent (override with
`LEDGERLENS_MODEL`); the point of the project is that the **workflow**, not a
bigger model, produces the improvement.

## 2. Get the code

```
git clone https://github.com/Amansingh1007/ledgerlens-hackathon.git
cd ledgerlens-hackathon
```

## 3. Sanity-check the evaluation data (no LLM calls)

```
python src/check_data.py
```
Expected: `OK` for all 14 ground-truth files. This proves every ground-truth
record is arithmetically self-consistent, so validator failures during runs can
only come from model output.

## 4. Run the baseline

```
python src/run_stage.py --stage baseline
python src/evaluate.py runs/baseline
```
Expected: ~14 LLM calls, a per-invoice score table, and a field accuracy in
the low-to-mid 90s% (LLM outputs vary slightly run to run; the losses
concentrate on inv_07, inv_11, and inv_14 — the cases whose answers are not
derivable from the single document, plus the corrupted printed total).

## 5. Run the final solution

```
python src/run_stage.py --stage final
python src/evaluate.py runs/final
```
Expected: 14–20 LLM calls (corrections fire only when the validator finds an
inconsistency), field accuracy at or near 100% (both of our runs of this
configuration scored 126/126), and `vendor_memory.json` inside `runs/final/`
showing the learned profiles — Meridian Supply (DD.MM.YYYY dates, 19%
tax-inclusive pricing) and Fairview Trading (day-first dates, SGD).

## 6. (Optional) Reproduce every changelog stage

```
python src/run_stage.py --stage context   && python src/evaluate.py runs/context
python src/run_stage.py --stage verify    && python src/evaluate.py runs/verify
python src/run_stage.py --stage memory    && python src/evaluate.py runs/memory
python src/run_stage.py --stage judge     && python src/evaluate.py runs/judge
python src/report.py        # aggregates all runs into RESULTS.md
```

The replay experiment (iteration 2's isolated contribution — feeds the
baseline's actual faulty extractions through the validator + corrector):

```
python src/replay_validator.py runs/baseline
```
Expected: 2 extractions detected as arithmetically inconsistent (inv_08,
inv_11) and both fully corrected; inv_03/07/14 reported as validator-invisible
(they are internally consistent — that is what iterations 1 and 3 are for).

## 7. (Optional) Run the interactive web app

```
python app.py
```
Open http://localhost:8765 — paste an invoice or load a sample, click
**Extract & verify**, and watch the live pipeline (memory lookup, extraction,
validator verdicts, corrections) beside the final JSON and learned vendor
profiles. Same engine rules as the harness (CLI or API key). Each extraction
takes 10–40 s. `webapp_memory.json` holds the app's learned vendor profiles;
delete it to reset.

## 8. What to look at

- `runs/<stage>/results.json` — machine-readable scores per field per invoice.
- `runs/<stage>/trajectory_inv_XX.jsonl` — the full agent trajectory: every
  prompt, model reply, validator verdict, retry, memory read/write, and
  human-review flag, in order.
- `RESULTS.md` — the stage-by-stage comparison table.
- `trajectories/` — curated representative trajectories with commentary.

## Data

All 14 invoices in `data/invoices/` are **synthetic** and were authored for this
project (no real companies, people, or amounts). Ground truth lives in
`data/ground_truth/`. No credentials or private data are used anywhere.

## Approximate cost

With Claude Haiku 4.5: ~100 short LLM calls for all six stages ≈ **well under $1**
via API, or $0 marginal cost on a Claude subscription via the CLI engine.
One stage (baseline or final) is ~14–20 calls, roughly 3–6 minutes.

## Determinism note

LLM sampling is not fully deterministic, so exact field-accuracy numbers can
shift by a point or two between runs. The *relative* result is stable across
reruns by construction: inv_07's net subtotal, inv_14's date/vendor/currency
are **not derivable from the single document** — no one-shot prompt can get
them right except by luck — while the validator loop deterministically catches
inv_11's corrupted total. The evaluator itself (`src/evaluate.py`) is fully
deterministic.
