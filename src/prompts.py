"""All prompts used by the baseline and the agent, in one place."""

SCHEMA = """{
  "vendor_name": "string",
  "invoice_number": "string",
  "invoice_date": "YYYY-MM-DD",
  "due_date": "YYYY-MM-DD or null if not applicable",
  "currency": "3-letter ISO code",
  "subtotal": 0.00,
  "tax_amount": 0.00,
  "total": 0.00,
  "line_items": [
    {"description": "string", "quantity": 0, "unit_price": 0.00, "amount": 0.00}
  ]
}"""

# ---------------------------------------------------------------- baseline --
# A reasonable "first thing you'd try": one direct prompt with the schema.

BASELINE_PROMPT = """Extract the invoice data from the document below into JSON with exactly this schema:

{schema}

Note: subtotal means all pre-tax charges (including shipping and after discounts).

Return only the JSON object, nothing else.

DOCUMENT:
{document}
"""

# ------------------------------------------------------------------- agent --
# Iteration 1: engineered context — explicit domain rules for the failure
# modes that real OCR'd invoices exhibit.

EXTRACT_PROMPT = """You are an invoice data-entry specialist. Extract the document below into JSON with exactly this schema:

{schema}

Rules:
1. OCR noise: the text may confuse O<->0 and l/I<->1 (e.g. "6O3" is 603, "Inv0ice" is "Invoice"). Repair obvious OCR damage in numbers, identifiers, and the vendor name.
2. Dates: output ISO YYYY-MM-DD. European documents commonly use DD.MM.YYYY. If no due date is printed but terms are given (e.g. "Net 30", "payable within 14 days"), compute due_date = invoice_date + that many days. Use null only when a due date truly does not apply (e.g. credit notes).
3. subtotal = ALL pre-tax charges: goods + shipping/fees, after discounts. tax_amount = tax only. total = subtotal + tax_amount. These three must be arithmetically consistent.
4. Tax-inclusive pricing: if the document says prices include VAT/tax (e.g. "inkl. MwSt."), the printed amounts are gross. Then subtotal = gross / (1 + rate) and tax_amount = gross - subtotal, rounded to 2 decimals. Line items still stay EXACTLY as printed (gross) — never convert item quantities, unit prices, or amounts to net.
5. Credit notes: quantities and amounts are NEGATIVE (money flows back to the customer).
6. Line items: one entry per billed line, including shipping lines and discount lines (discounts have negative amounts). "Carried forward" / "brought forward" page totals are NOT line items.
7. currency = the currency the invoice is payable in. Ignore courtesy conversions ("approx. USD ...").
8. vendor_name = the party ISSUING the invoice, in clean canonical spelling.
{memory_hints}
Return only the JSON object, nothing else.

DOCUMENT:
{document}
"""

CORRECTION_PROMPT = """You are an invoice data-entry specialist. You previously extracted the JSON below from the document, but an automated validator found problems.

DOCUMENT:
{document}

YOUR PREVIOUS EXTRACTION:
{previous}

VALIDATOR ERRORS:
{errors}

Fix the extraction. Re-read the document carefully, repair any OCR digit damage (O<->0, l/I<->1), and make subtotal + tax_amount = total and the line items reconcile. Keep the same schema. Return only the corrected JSON object, nothing else.
"""

# --------------------------------------------------------- judge (removed) --
# Iteration 4 experiment: a second-opinion LLM judge. Measured, then removed
# — see the Improvement Changelog.

JUDGE_PROMPT = """You are a meticulous accounting reviewer. Review this extraction against the source document.

DOCUMENT:
{document}

EXTRACTION:
{extraction}

If the extraction is fully correct, reply with exactly:
{{"verdict": "approve"}}

If anything is wrong, reply with:
{{"verdict": "revise", "revised": <the corrected full extraction JSON>}}

Return only JSON.
"""
