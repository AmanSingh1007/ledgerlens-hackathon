"""Vendor memory: consistency across invoices from the same vendor.

After each successfully validated extraction, LedgerLens stores a small
vendor profile (canonical name, currency, tax style, observed date format).
On later invoices it fuzzy-matches the document header against known vendors
— which survives OCR-mangled names — and injects the profile into the
extraction prompt as hints.
"""

import difflib
import json
import os
import re


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


class VendorMemory:
    def __init__(self, path):
        self.path = path
        self.profiles = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.profiles = json.load(f)

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.profiles, f, indent=2)

    def lookup(self, raw_text: str):
        """Match the top of the document against known vendor names."""
        header = " ".join(raw_text.strip().splitlines()[:3])
        header_n = _norm(header)
        best, best_score = None, 0.0
        for p in self.profiles:
            name_n = _norm(p["canonical_name"])
            if not name_n:
                continue
            # Slide the vendor name across the header and keep the best ratio.
            score = max(
                (difflib.SequenceMatcher(None, name_n, header_n[i:i + len(name_n)]).ratio()
                 for i in range(0, max(1, len(header_n) - len(name_n) + 1), 4)),
                default=0.0,
            )
            if score > best_score:
                best, best_score = p, score
        return best if best_score >= 0.75 else None

    def hints_for(self, profile) -> str:
        lines = [f"- Canonical vendor name: {profile['canonical_name']} "
                 f"(use exactly this spelling even if OCR mangled it)"]
        if profile.get("currency"):
            lines.append(f"- This vendor bills in {profile['currency']}.")
        if profile.get("date_format"):
            lines.append(f"- This vendor prints dates as {profile['date_format']}.")
        if profile.get("prices_include_tax"):
            lines.append(f"- This vendor's printed prices INCLUDE tax "
                         f"(rate {profile.get('tax_rate', '?')}). "
                         f"Derive net subtotal = total / (1 + rate).")
        return "Known vendor profile (learned from previously processed invoices):\n" + "\n".join(lines)

    def update(self, result: dict, raw_text: str):
        """Record/refresh a profile from a validated extraction."""
        name = result.get("vendor_name")
        if not name:
            return
        profile = None
        for p in self.profiles:
            if _norm(p["canonical_name"]) == _norm(name):
                profile = p
                break
        if profile is None:
            profile = self.lookup(raw_text)
        if profile is None:
            profile = {"canonical_name": name}
            self.profiles.append(profile)

        profile["currency"] = result.get("currency")

        subtotal = result.get("subtotal") or 0
        tax = result.get("tax_amount") or 0
        items = result.get("line_items") or []
        item_sum = sum(it.get("amount", 0) for it in items if isinstance(it, dict))
        if subtotal and tax:
            profile["tax_rate"] = round(tax / subtotal, 4)
            # If line items reconcile with the gross total, prices are tax-inclusive.
            profile["prices_include_tax"] = abs(item_sum - (subtotal + tax)) <= 0.02 < abs(item_sum - subtotal)

        # Infer the printed date format from the raw text (DD.MM.YYYY, DD/MM/YYYY, ...)
        m = re.search(r"\b(\d{2})([./])(\d{2})\2(\d{4})\b", raw_text)
        if m and result.get("invoice_date"):
            d, sep, mo, y = m.groups()
            if result["invoice_date"] == f"{y}-{mo}-{d}":
                profile["date_format"] = f"DD{sep}MM{sep}YYYY (day first)"

        self._save()
