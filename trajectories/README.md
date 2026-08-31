# Agent Trajectories

Every run writes a complete, ordered trajectory for every invoice to
`runs/<stage>/trajectory_inv_XX.jsonl` — one JSON event per line:

| `step` | Meaning |
|---|---|
| `memory_read` | Vendor-memory lookup result (a profile, or `null` for an unknown vendor) |
| `prompt` | Exact prompt sent to the LLM (`role`: extractor / corrector / judge) |
| `response` | Exact model reply |
| `validation` | Deterministic validator verdict — the list of errors (empty = pass) |
| `judge_applied` / `judge_rejected` | What happened to a judge's proposed revision |
| `human_review_flag` | Extraction could not be reconciled; routed to a person with reasons |
| `memory_write` | Vendor profile stored/updated after a validated extraction |

The curated copies in this folder are the representative trajectories asked
for in the deliverables — real, unedited files from the evaluation runs,
chosen to show each mechanism doing (or failing to do) real work:

- **`final-config_inv_02.jsonl` — the validator earning its keep.** The
  extractor copied the OCR-transposed line amount (108.00 instead of
  12 × 8.40 = 100.80). The `validation` event shows both deterministic
  catches (`quantity 12 x unit_price 8.4 = 100.80, but amount is 108.00`;
  `line item sum 558.00 matches neither subtotal 550.80 nor total 603.13`),
  the corrector receives those exact strings, and the second `validation`
  event is clean.
- **`final-config_inv_07.jsonl` — vendor memory in action.** The
  `memory_read` event shows the profile learned from inv_03 (canonical
  "Meridian Supply GmbH", DD.MM.YYYY dates, 19% tax-inclusive pricing)
  injected before extraction of the OCR-mangled invoice whose tax-inclusive
  footer is torn off — the only way to book the correct net subtotal 200.50.
- **`final-config_inv_14.jsonl` — memory canonicalizing a vendor.** The
  profile learned from inv_13 supplies the full vendor name and SGD currency
  for an invoice that only says "FAIRVIEW TRDG PTE LTD" and "$".
- **`baseline_inv_07.jsonl` — the same hard invoice under the baseline**, for
  contrast: one prompt, no memory, no second chance — it books the gross
  238.60 as the subtotal with zero tax, and nothing flags it.
- **`judge_inv_14.jsonl` — the removed iteration-4 experiment.** The LLM
  judge reviews a correct extraction and "fixes" it backwards: it reverts the
  canonical vendor name to the printed abbreviation. Its revision passes the
  arithmetic validator (names aren't arithmetic), so the damage lands. This
  file is why iteration 4 was removed.

Each file is self-contained: read it top to bottom and you can follow the
agent from its instructions to its final result, including every tool
response, retry, and checkpoint.
