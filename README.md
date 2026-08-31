# LedgerLens — an agentic invoice-extraction workflow that checks its own math

*micro1 Agentic Workflows Hackathon submission*

## Who has this problem?

Bookkeepers and small-business finance-ops teams. Accounts-payable clerks at
small firms key data from supplier invoices — often scanned/OCR'd documents —
into accounting software by hand. A typical AP clerk processes dozens of
invoices a day, and each one means transcribing a vendor, dates, currency,
line items, tax, and totals without error, because these numbers flow straight
into payments, tax filings, and the general ledger.

## What bottleneck makes it worth solving?

Manual invoice entry is slow (industry surveys put it at ~5 minutes per
invoice) and the failure modes are nasty precisely because they're quiet:

- **OCR noise** — `O`↔`0` and `l`↔`1` swaps silently corrupt totals and invoice numbers.
- **Ambiguous dates** — is `04.12.2025` April 12 or December 4? Depends on the vendor.
- **Tax-inclusive pricing** — EU invoices print gross amounts ("inkl. 19% MwSt."); the net subtotal your ledger needs isn't printed anywhere.
- **Credit notes** — a positive-signed credit note overstates payables twice over.
- **Traps** — courtesy currency conversions, "carried forward" page totals, shipping taxed differently from goods.

A naive "just ask an LLM for JSON" pass gets the easy 80% right and fails on
exactly these cases — and it fails *silently*, which for accounting data is
worse than not automating at all.

## The solution

LedgerLens is a pipeline of purposeful agentic components. Each one exists
because a measured failure demanded it (see the changelog):

```
                      ┌────────────────────────────────────────────┐
                      │              VENDOR MEMORY                 │
                      │  canonical name · date format · tax style  │
                      └───────▲───────────────────────────┬────────┘
                       write  │                    read   │ (fuzzy header match,
                  (validated  │                           │  survives OCR damage)
                   runs only) │                           ▼
 OCR'd invoice ──────► EXTRACTOR (LLM) ──► DETERMINISTIC VALIDATOR ──► pass ──► JSON out
                              ▲             (schema, dates, and         │
                              │              arithmetic identities:     │ fail (×2 max)
                              │              qty×price=amount,          ▼
                              │              Σitems=subtotal|total,   CORRECTOR (LLM,
                              │              subtotal+tax=total)      sees exact errors)
                              │                                         │
                              └─────────────────────────────────────────┘
                                     still failing after 2 retries
                                                  │
                                                  ▼
                                    needs_human_review = true
                                    + machine-readable reasons
```

**Design choices, and why each one is there:**

1. **Deterministic verification instead of LLM self-critique.** A correct
   extraction must satisfy arithmetic identities (`qty × price = amount`,
   `subtotal + tax = total`, `Σ line items = subtotal` or `= total`) that can
   be checked in pure Python with zero false authority. The validator never
   sees ground truth — it only checks internal consistency — and it caught
   100% of the arithmetically-inconsistent errors we observed (OCR-corrupted
   amounts and totals), at zero LLM cost whenever nothing is wrong. What it
   *cannot* see — internally-consistent wrongness — is precisely what memory
   and the human checkpoint are for.
2. **The corrector sees the *specific* error**, not "try again" — e.g.
   `subtotal 550.80 + tax 52.33 = 603.13, but total is 603.10`. Targeted
   feedback converts almost every validator failure in one retry.
3. **Vendor memory for cross-invoice consistency.** Some facts are not on the
   invoice at all: that Meridian Supply writes dates DD.MM.YYYY, prices
   tax-inclusive at 19%, and is called "Meridian Supply GmbH" even when OCR
   prints "MERIDlAN SUPPLY GMBH". LedgerLens learns a vendor profile from each
   *validated* extraction and injects it into future extractions via fuzzy
   header matching. Only validated runs may write memory, so errors can't
   self-reinforce.
4. **A human checkpoint by design.** Anything the loop cannot reconcile is
   flagged `needs_human_review` with machine-readable reasons instead of being
   silently emitted. LedgerLens extracts and flags; it never posts to a ledger
   or moves money — the consequential action stays with a person.

## Evaluation

- **Dataset:** 14 synthetic OCR-style invoices (`data/invoices/`) with ground
  truth (`data/ground_truth/`), authored for this project. They cover the real
  failure modes above: clean invoices, OCR noise, tax-inclusive EU invoices, a
  discount, a credit note, a two-page invoice, a missing subtotal, goods-only
  tax, per-line rounding, a currency-conversion trap, an OCR-transposed
  printed total that contradicts the (correct) line items, and two cases that
  are **provably unsolvable from the single document** — a torn-off
  tax-inclusive notice and an ambiguous `05/04/2025` date + abbreviated vendor
  + unstated currency — resolvable only from that vendor's earlier invoices.
  `src/check_data.py` proves every ground-truth record passes the validator,
  so the data itself is sound.
- **Primary metric:** field-level accuracy over 9 fields × 14 invoices =
  **126 field checks** (vendor, invoice number, dates, currency, subtotal,
  tax, total, line items). Scoring (`src/evaluate.py`) is fully deterministic:
  normalized strings, ±0.01 on numbers.
- **Fairness:** baseline and agent get the *same model*
  (`claude-haiku-4-5-20251001`), the same 14 documents, and the same target
  schema. The only difference is the workflow around the model.

### Results

| Metric | Simple baseline | Agent solution (final) | Change |
|---|---|---|---|
| **Field accuracy (primary)** | 120/126 (95.2%) | **126/126 (100%)** | **+6 fields, +4.8 pts** |
| Invoices fully correct | 9/14 | **14/14** | +5 invoices |
| Silent errors (wrong fields, no warning) | 6 wrong fields on 5 invoices, **0 flagged** | **0** | eliminated |
| Human time per invoice | ~5 min manual entry, or re-check *every* AI draft | spot-check only what the validator flags | reviewer attention goes only where evidence says |
| LLM calls per invoice | 1.0 | 1.0–1.1 (corrections fire only on validator errors) | ≤ +7% calls for the accuracy gain |

The five baseline-failed invoices are exactly the designed hard cases, and each
one fails *silently* — the number is wrong and nothing warns you:
tax-inclusive line items converted to invented net amounts (inv_03), an
OCR-transposed line amount copied verbatim (inv_08), a corrupted printed total
copied verbatim (inv_11), a gross total booked as the net subtotal because the
tax notice is torn off (inv_07), and an abbreviated vendor name kept as-is
(inv_14).

Full per-invoice, per-field detail: [`RESULTS.md`](RESULTS.md) and `runs/*/results.json`.

## Improvement Changelog

| Stage | What we tried and why | Evidence (same invoices, same model) | Decision / learning |
|---|---|---|---|
| **Eval v1 (rejected)** | First evaluation set: 12 invoices with OCR noise, tax-inclusive EU pricing, a credit note, and culturally-cued ambiguous dates. | Baseline one-shot scored **108/108 (100%)** — so did every other stage. | **Hardened the eval.** A modern model one-shots invoice hard cases whose answer is still derivable from the document. A saturated eval measures nothing, so we redesigned it around *information asymmetry*: cases where the correct answer provably isn't in the document (torn-off tax notice, ambiguous date + abbreviated vendor + unstated currency for a known vendor) plus an OCR-corrupted printed total that contradicts the correct line items. |
| **Baseline** (final eval) | Same direct prompt with the target schema — the reasonable first thing anyone would build. | **120/126 fields (95.2%)**, 9/14 invoices fully correct, all 6 wrong fields silent (0 flagged). | Established the starting point. The model faithfully *transcribes* corruption (copies a transposed 108.00 and a corrupted total 215.24 verbatim), converts tax-inclusive line items to invented net amounts, books a gross total as the net subtotal when the tax notice is torn off, and keeps an abbreviated vendor name. |
| **Iteration 1 — engineered context** | Added explicit domain rules to the prompt (OCR repair, date semantics, tax-inclusive math, credit-note signs, subtotal definition) after reading baseline failures. | **123/126 (97.6%)**; repeat runs: 123 and 124/126 (12/14 fully correct). | **Kept — biggest single jump.** The first version *introduced a regression*: it converted tax-inclusive line items to invented net amounts (inv_03). One added rule ("line items stay exactly as printed") fixed it. Remaining failures are all cases whose answer is not in the document. |
| **Iteration 2 — deterministic validator + correction loop** | Arithmetic identities (`qty×price=amount`, `Σitems=subtotal\|total`, `subtotal+tax=total`) checked in pure Python; exact error strings fed back to a corrector (max 2 retries); unresolved → human-review flag. | Same-sample accuracy unchanged (123/126) — the contexted extractor happened to produce consistent output that run. **Replay on the baseline's actual faulty outputs: 2/2 arithmetically-inconsistent extractions detected and both fully corrected** (inv_08, inv_11 → `runs/replay/`). In the iteration-3 run it caught a **live slip** (inv_02: extractor copied the transposed 108.00; one correction round fixed it — see `trajectories/final-config_inv_02.jsonl`). | **Kept.** Extraction slips are stochastic; the validator converts "usually right" into "checked right" at zero LLM cost when nothing is wrong, and it is the only component that can *flag* an unreconcilable document for a human instead of silently emitting it. |
| **Iteration 3 — vendor memory** | Added after observing failures *impossible* to fix from a single document: inv_07's net subtotal hides behind a torn-off "prices include 19% VAT" notice, and inv_14 says only "FAIRVIEW TRDG PTE LTD" and "$". Profiles are learned from validated extractions only and injected via fuzzy header matching. | **126/126 (100%), 14/14 fully correct**, 15 LLM calls. | **Kept.** Closed the last 3 fields, all provably unanswerable from the lone document. Write-gating memory on validation matters: it stops one bad extraction from poisoning every later invoice from that vendor. |
| **Iteration 4 — LLM judge (second opinion)** | A reviewer agent re-reads every extraction and may propose a revision, hoping to catch content errors arithmetic can't see. | **125/126 (99.2%) at 29 LLM calls (~2× cost).** The judge took a *correct* result and reverted the canonical vendor name back to the printed abbreviation; the revision passed the arithmetic validator (names aren't arithmetic) and the damage landed — `trajectories/judge_inv_14.jsonl`. | **Removed.** It doubled cost and the only answers it changed, it changed for the worse. A second opinion from the same model adds correlated error, not information. |
| **Final** | Engineered context + validator loop + vendor memory. | **126/126 (100%), 14/14 fully correct, 0 silent errors,** ~1.1 calls/invoice. | Main contribution split: context engineering (+3–4 fields), vendor memory (+3 fields), and the validator as the deterministic safety net that catches stochastic slips and gates both memory writes and human escalation. |

## Main failure mode

**Internally-consistent wrongness.** Every check we can compute — schema,
dates, arithmetic — passes on an extraction that is still wrong, whenever the
document itself doesn't contain the truth: inv_07 with its tax notice torn off
validates perfectly as a zero-tax invoice; inv_14's abbreviated vendor name is
a perfectly plausible string. No single-document workflow, however clever, can
fix these; they need external knowledge (here: vendor memory) or a human. The
judge experiment showed the trap of reaching for "more LLM" instead: a
same-model second opinion *un-fixed* a correct answer and slipped past the
validator, because the validator can only defend what it can compute.

## Hot take

**The model ate our verifier — and the eval had to get harder to notice what
was left.** We built this expecting the deterministic validator to do the
heavy lifting. Our first eval said otherwise, twice. First, a modern model
one-shot 100% of an invoice benchmark whose hard cases were merely *hard* —
OCR noise, credit-note signs, tax-inclusive math — so we rebuilt the eval
around cases whose answers provably aren't in the document. Second, even
then, a well-contexted extractor produced arithmetically consistent output in
almost every run, so the validator sat idle in the happy path; its measured
value showed up only in replay (it caught and fixed 2/2 of the baseline's
arithmetic errors) and in one live stochastic slip. Meanwhile an LLM judge —
the thing that *feels* like verification — made results strictly worse at 2×
cost. The lesson we'd build on next time: put your engineering into the
context the model reads, the memory that carries facts between documents, and
cheap deterministic checks that gate memory-writes and human escalation.
Treat verification as insurance and an escalation gate, not as the engine of
quality — and never spend a second LLM call to get an opinion correlated with
the first one.

## Repository map

```
data/invoices/       14 synthetic OCR-style invoices (the eval set)
data/ground_truth/   ground truth JSON per invoice
src/llm.py           engine: Claude Code CLI (`claude -p`) or Anthropic API
src/prompts.py       every prompt (baseline, extractor, corrector, judge)
src/validator.py     deterministic schema/date/arithmetic checks
src/memory.py        vendor memory: learn + fuzzy-match profiles
src/agent.py         the pipeline (extract → validate → correct → memory)
src/run_stage.py     run any changelog stage end to end
src/evaluate.py      deterministic scoring vs ground truth
src/report.py        aggregate all stages into RESULTS.md
src/replay_validator.py  replay validator+corrector on observed faulty outputs
src/check_data.py    prove the eval data is internally consistent
runs/                outputs: extractions, trajectories, results per stage
trajectories/        curated representative trajectories (see its README)
```

## Provenance & ground rules

Everything in this repository was written during the hackathon. Pre-existing
components: Python 3.11, Claude Code CLI / Anthropic API (used per their
terms), and the pinned model `claude-haiku-4-5-20251001`. All invoice data is
synthetic — no real companies, people, amounts, or credentials appear anywhere.
The workflow takes no consequential actions: it reads documents and emits
JSON plus human-review flags; posting to any real ledger is deliberately out
of scope and would sit behind the human checkpoint.

## Reproduce it

See [REPRODUCE.md](REPRODUCE.md) — clean-environment setup, exact commands for
baseline, final, every changelog stage, and the evaluation; expected outputs,
runtime, and cost.
