from decimal import Decimal

import pytest

from app.services.seat_tier_import import parse_seat_tier_csv


def test_mixed_case_duplicate_keeps_last_valid_price():
    report = parse_seat_tier_csv('tier_name,price\nSilver,₹120\nSILVER,"1,200.50"\nsilver,Rs. 220\n')

    assert [(item.tier_name, item.price) for item in report.imported] == [("Silver", Decimal("220.00"))]
    assert [(item.discarded_row, item.winning_row) for item in report.deduplicated] == [(2, 3), (3, 4)]


def test_rejects_blank_negative_and_unparseable_prices():
    report = parse_seat_tier_csv(
        "tier_name,price\nSilver,\nGold,-10\nRecliner,not-money\n"
    )

    assert not report.imported
    assert [item.reason for item in report.rejected] == [
        "price is blank",
        "price cannot be negative",
        "price is not a valid number",
    ]


def test_zero_price_is_valid():
    report = parse_seat_tier_csv("tier_name,price\nComplimentary,0\n")

    assert report.imported[0].tier_name == "Complimentary"
    assert report.imported[0].price == Decimal("0.00")


def test_rejects_missing_columns():
    with pytest.raises(ValueError, match="tier_name and price"):
        parse_seat_tier_csv("name,cost\nSilver,120\n")
