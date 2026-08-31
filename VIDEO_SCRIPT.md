# Solution Video — 5-minute script / shot list

*(Helper for recording the deliverable-3 video. Record your screen + voice;
OBS Studio, Loom, or Windows Game Bar (Win+Alt+R) all work.)*

**0:00–0:40 — The problem.**
Show `data/invoices/inv_02.txt` and `inv_07.txt` side by side.
Say: "AP clerks key OCR'd invoices into accounting software by hand — about
5 minutes each. The failure modes are quiet: OCR turns 0 into O, EU invoices
print tax-inclusive prices with no net subtotal, and `04.12.2025` is only
December 4th if you know this vendor. Wrong numbers here flow into payments
and tax filings."

**0:40–1:20 — The baseline.**
Run: `python src/evaluate.py runs/baseline`
Say: "The obvious first solution — one prompt with the schema, same model as
the final system. 120 of 126 fields, 9 of 14 invoices fully correct — and all
six wrong fields are silent." Point at the X marks on inv_03/07/08/11/14.

**1:20–3:00 — One realistic execution, start to finish.**
Run: `python src/run_stage.py --stage final` (or pre-recorded; it takes a few
minutes) then open `runs/final/trajectory_inv_07.jsonl`.
Walk through the events in order:
1. `memory_read` — "the fuzzy header match recognized the OCR-mangled
   'MERIDlAN SUPPLY GMBH' and pulled the profile it learned four invoices ago:
   canonical name, DD.MM.YYYY dates, 19% tax-inclusive pricing."
2. extractor `prompt`/`response` — "the hints are injected into the prompt."
3. `validation` — "then a deterministic validator checks arithmetic identities
   — qty×price, subtotal+tax=total, line-item reconciliation. Pure Python,
   can't hallucinate." (If a correction round exists, show the exact error
   message the corrector received.)
4. `memory_write` — "validated results update the vendor profile."
Also flash `runs/final/vendor_memory.json`.

**3:00–3:50 — The comparison.**
Show `RESULTS.md`.
Say the headline numbers: baseline 120/126 (95.2%) and 9/14 invoices fully
correct, final 126/126 (100%) and 14/14 — across two independent runs — and
that anything unreconcilable gets flagged for human review instead of
silently emitted.

**3:50–4:40 — Changelog: what mattered and what we removed.**
Show the changelog table in README.md.
Say: "Biggest single win: engineered context — plus vendor memory, which
closed the three fields that provably aren't in the document. The validator's
value showed up differently: it sat idle when extraction was right, caught a
live stochastic slip, and in replay it detected and fixed 100% of the
baseline's arithmetic errors. And one experiment we removed: an LLM judge that
re-reviewed every extraction — it doubled cost and un-fixed a correct vendor
name. Verification you can compute beats verification you can prompt."

**4:40–5:00 — Close.**
"Everything is reproducible from a clean environment with either a Claude
Code login or an API key — REPRODUCE.md has the exact commands. Thanks!"
