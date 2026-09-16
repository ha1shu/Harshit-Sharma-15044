from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


Q = Decimal("0.01")


def _q(value: Decimal) -> Decimal:
    return value.quantize(Q, rounding=ROUND_HALF_UP)


def _sum(values):
    total = Decimal("0.00")
    for value in values:
        total += value
    return _q(total)


def calculate_booking_breakup(
    line_items,
    festival_discount: Decimal = Decimal("0.00"),
    membership_percent: Decimal = Decimal("0.00"),
    membership_cap: Decimal = Decimal("0.00"),
    convenience_fee_per_ticket: Decimal = Decimal("0.00"),
    gst_rate: Decimal = Decimal("0.18"),
):
    subtotal = _sum(
        Decimal(str(quantity)) * price for _, quantity, price in line_items
    )

    flat_discount = min(_q(festival_discount), subtotal)
    running_after_flat = _q(subtotal - flat_discount)

    if membership_percent > 0:
        membership_discount_raw = running_after_flat * (membership_percent / Decimal("100"))
        membership_discount = min(_q(membership_discount_raw), _q(membership_cap))
    else:
        membership_discount = Decimal("0.00")

    discounted_subtotal = _q(max(Decimal("0.00"), running_after_flat - membership_discount))

    total_tickets = sum(quantity for _, quantity, _ in line_items)
    convenience_fee = _q(convenience_fee_per_ticket * Decimal(total_tickets))
    taxable_base = _q(discounted_subtotal + convenience_fee)

    cgst = _q(taxable_base * (gst_rate / Decimal("2")))
    sgst = _q(taxable_base * (gst_rate / Decimal("2")))
    grand_total = _q(discounted_subtotal + convenience_fee + cgst + sgst)

    line_items_out = [
        {"kind": "subtotal", "label": "Subtotal", "amount": _q(subtotal)},
        {"kind": "discount", "label": "Festival discount", "amount": -_q(flat_discount)},
        {"kind": "discount", "label": "Membership discount", "amount": -_q(membership_discount)},
        {"kind": "fee", "label": "Convenience fee", "amount": _q(convenience_fee)},
        {"kind": "tax", "label": "CGST", "amount": _q(cgst)},
        {"kind": "tax", "label": "SGST", "amount": _q(sgst)},
    ]

    return {
        "subtotal": _q(subtotal),
        "flat_discount": _q(flat_discount),
        "membership_discount": _q(membership_discount),
        "discounted_subtotal": _q(discounted_subtotal),
        "convenience_fee": _q(convenience_fee),
        "cgst": _q(cgst),
        "sgst": _q(sgst),
        "grand_total": _q(grand_total),
        "line_items": line_items_out,
    }
