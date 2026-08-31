"""Deterministic validator: the agent's ground-truth-free error detector.

Every check here is a property a correct invoice extraction MUST satisfy
regardless of what the true values are (schema shape, date syntax, and
internal arithmetic consistency). It never sees the ground truth.
"""

import datetime
import re

TOL = 0.02

REQUIRED = {
    "vendor_name": str,
    "invoice_number": str,
    "invoice_date": str,
    "currency": str,
    "subtotal": (int, float),
    "tax_amount": (int, float),
    "total": (int, float),
    "line_items": list,
}

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_iso(s):
    if not isinstance(s, str) or not ISO_DATE.match(s):
        return False
    try:
        datetime.date.fromisoformat(s)
        return True
    except ValueError:
        return False


def validate(inv: dict) -> list:
    """Return a list of human-readable error strings (empty = passes)."""
    errors = []

    for field, typ in REQUIRED.items():
        if field not in inv or inv[field] is None:
            errors.append(f"Missing required field: {field}")
        elif not isinstance(inv[field], typ):
            errors.append(f"Field {field} has wrong type: expected {typ}, got {type(inv[field]).__name__}")
    if errors:
        return errors  # structural problems make the rest meaningless

    if not re.match(r"^[A-Z]{3}$", inv["currency"]):
        errors.append(f"currency must be a 3-letter ISO code like USD, got: {inv['currency']!r}")

    if not _is_iso(inv["invoice_date"]):
        errors.append(f"invoice_date must be YYYY-MM-DD, got: {inv['invoice_date']!r}")
    due = inv.get("due_date")
    if due is not None:
        if not _is_iso(due):
            errors.append(f"due_date must be YYYY-MM-DD or null, got: {due!r}")
        elif _is_iso(inv["invoice_date"]) and due < inv["invoice_date"]:
            errors.append(f"due_date {due} is before invoice_date {inv['invoice_date']}")

    items = inv["line_items"]
    if not items:
        errors.append("line_items is empty")
        return errors

    item_sum = 0.0
    for i, it in enumerate(items, 1):
        if not isinstance(it, dict):
            errors.append(f"line_items[{i}] is not an object")
            continue
        for k in ("description", "quantity", "unit_price", "amount"):
            if k not in it:
                errors.append(f"line_items[{i}] missing key: {k}")
        if not all(k in it for k in ("quantity", "unit_price", "amount")):
            continue
        q, u, a = it["quantity"], it["unit_price"], it["amount"]
        if not all(isinstance(v, (int, float)) for v in (q, u, a)):
            errors.append(f"line_items[{i}] quantity/unit_price/amount must be numbers")
            continue
        if abs(q * u - a) > TOL:
            errors.append(
                f"line_items[{i}] arithmetic: quantity {q} x unit_price {u} = {q * u:.2f}, "
                f"but amount is {a:.2f}"
            )
        item_sum += a

    subtotal, tax, total = inv["subtotal"], inv["tax_amount"], inv["total"]

    if abs(subtotal + tax - total) > TOL:
        errors.append(
            f"totals arithmetic: subtotal {subtotal:.2f} + tax {tax:.2f} = "
            f"{subtotal + tax:.2f}, but total is {total:.2f}"
        )

    # Line items must reconcile with either the net subtotal (tax-exclusive
    # pricing) or the gross total (tax-inclusive pricing, common in the EU).
    if abs(item_sum - subtotal) > TOL and abs(item_sum - total) > TOL:
        errors.append(
            f"line item sum {item_sum:.2f} matches neither subtotal {subtotal:.2f} "
            f"nor total {total:.2f}. Check for missed/duplicated lines, OCR digit errors, "
            f"or whether printed prices are tax-inclusive (then subtotal = total / (1 + rate))."
        )

    return errors
