from decimal import Decimal

import pytest

from app.pricing.engine import calculate_booking_breakup


@pytest.mark.parametrize(
    "items, festival_discount, membership_percent, membership_cap, expected_total",
    [
        ([("Silver", 2, Decimal("120.00"))], Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), Decimal("330.40")),
        ([("Silver", 2, Decimal("120.00"))], Decimal("50.00"), Decimal("0.00"), Decimal("0.00"), Decimal("271.40")),
        ([("Silver", 2, Decimal("120.00"))], Decimal("0.00"), Decimal("10.00"), Decimal("30.00"), Decimal("302.08")),
        ([("Silver", 2, Decimal("120.00"))], Decimal("50.00"), Decimal("10.00"), Decimal("30.00"), Decimal("248.98")),
    ],
)
def test_calculate_booking_breakup(items, festival_discount, membership_percent, membership_cap, expected_total):
    result = calculate_booking_breakup(
        line_items=items,
        festival_discount=festival_discount,
        membership_percent=membership_percent,
        membership_cap=membership_cap,
        convenience_fee_per_ticket=Decimal("20.00"),
        gst_rate=Decimal("0.18"),
    )

    assert result["grand_total"] == expected_total
    assert result["grand_total"] == sum(item["amount"] for item in result["line_items"])


def test_multi_tier_and_discount_stack_rounding():
    result = calculate_booking_breakup(
        line_items=[
            ("Silver", 2, Decimal("200.00")),
            ("Gold", 1, Decimal("450.00")),
        ],
        festival_discount=Decimal("100.00"),
        membership_percent=Decimal("10.00"),
        membership_cap=Decimal("150.00"),
        convenience_fee_per_ticket=Decimal("20.00"),
        gst_rate=Decimal("0.18"),
    )

    assert result["subtotal"] == Decimal("850.00")
    assert result["flat_discount"] == Decimal("100.00")
    assert result["membership_discount"] == Decimal("75.00")
    assert result["grand_total"] == Decimal("867.30")
    assert sum(item["amount"] for item in result["line_items"]) == result["grand_total"]


def test_discount_does_not_go_negative():
    result = calculate_booking_breakup(
        line_items=[("Silver", 1, Decimal("50.00"))],
        festival_discount=Decimal("100.00"),
        membership_percent=Decimal("10.00"),
        membership_cap=Decimal("10.00"),
        convenience_fee_per_ticket=Decimal("5.00"),
        gst_rate=Decimal("0.18"),
    )

    assert result["grand_total"] == Decimal("5.90")
    assert result["discounted_subtotal"] == Decimal("0.00")
    assert sum(item["amount"] for item in result["line_items"]) == result["grand_total"]
