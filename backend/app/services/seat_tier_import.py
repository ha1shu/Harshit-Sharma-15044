from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TextIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SeatTier, Show


@dataclass(frozen=True)
class ImportedTier:
    tier_name: str
    price: Decimal
    row_number: int


@dataclass(frozen=True)
class RejectedRow:
    row_number: int
    tier_name: str
    raw_price: str
    reason: str


@dataclass(frozen=True)
class DeduplicatedTier:
    tier_name: str
    discarded_row: int
    discarded_price: Decimal
    winning_row: int
    winning_price: Decimal


@dataclass(frozen=True)
class SeatTierImportReport:
    imported: tuple[ImportedTier, ...]
    deduplicated: tuple[DeduplicatedTier, ...]
    rejected: tuple[RejectedRow, ...]

    def as_dict(self) -> dict:
        return {
            "imported": [
                {"tier_name": item.tier_name, "price": str(item.price), "row_number": item.row_number}
                for item in self.imported
            ],
            "deduplicated": [
                {
                    "tier_name": item.tier_name,
                    "discarded_row": item.discarded_row,
                    "discarded_price": str(item.discarded_price),
                    "winning_row": item.winning_row,
                    "winning_price": str(item.winning_price),
                }
                for item in self.deduplicated
            ],
            "rejected": [
                {
                    "row_number": item.row_number,
                    "tier_name": item.tier_name,
                    "raw_price": item.raw_price,
                    "reason": item.reason,
                }
                for item in self.rejected
            ],
        }


_CURRENCY_PREFIX = re.compile(r"^(?:rs\.?|inr)\s*", re.IGNORECASE)
_CURRENCY_SYMBOLS = re.compile(r"[₹$€£]")


def normalize_tier_name(value: str) -> str:
    return " ".join(value.strip().split()).title()


def parse_price(value: str) -> Decimal:
    cleaned = _CURRENCY_PREFIX.sub("", value.strip())
    cleaned = _CURRENCY_SYMBOLS.sub("", cleaned).replace(",", "").strip()
    if not cleaned:
        raise ValueError("price is blank")
    try:
        price = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("price is not a valid number") from exc
    if not price.is_finite():
        raise ValueError("price is not a valid number")
    if price < 0:
        raise ValueError("price cannot be negative")
    return price.quantize(Decimal("0.01"))


def parse_seat_tier_csv(source: TextIO | str) -> SeatTierImportReport:
    if isinstance(source, str):
        source = io.StringIO(source)

    reader = csv.DictReader(source)
    field_names = {name.strip() for name in (reader.fieldnames or []) if name}
    if not {"tier_name", "price"}.issubset(field_names):
        raise ValueError("CSV must contain tier_name and price columns")

    valid_by_name: dict[str, ImportedTier] = {}
    deduplicated: list[DeduplicatedTier] = []
    rejected: list[RejectedRow] = []

    for row_number, row in enumerate(reader, start=2):
        raw_name = row.get("tier_name") or ""
        raw_price = row.get("price") or ""
        tier_name = normalize_tier_name(raw_name)
        if not tier_name:
            rejected.append(RejectedRow(row_number, tier_name, raw_price, "tier name is blank"))
            continue

        try:
            price = parse_price(raw_price)
        except ValueError as exc:
            rejected.append(RejectedRow(row_number, tier_name, raw_price, str(exc)))
            continue

        current = ImportedTier(tier_name, price, row_number)
        previous = valid_by_name.get(tier_name.casefold())
        if previous is not None:
            deduplicated.append(
                DeduplicatedTier(
                    tier_name=tier_name,
                    discarded_row=previous.row_number,
                    discarded_price=previous.price,
                    winning_row=row_number,
                    winning_price=price,
                )
            )
        valid_by_name[tier_name.casefold()] = current

    imported = tuple(sorted(valid_by_name.values(), key=lambda item: item.row_number))
    return SeatTierImportReport(imported, tuple(deduplicated), tuple(rejected))


def apply_seat_tier_import(session: Session, show_id: int, report: SeatTierImportReport) -> list[SeatTier]:
    if session.get(Show, show_id) is None:
        raise ValueError(f"show {show_id} does not exist")

    existing_tiers = session.execute(select(SeatTier).where(SeatTier.show_id == show_id)).scalars().all()
    existing_by_name = {tier.tier_name.casefold(): tier for tier in existing_tiers}
    changed_tiers: list[SeatTier] = []

    for item in report.imported:
        key = item.tier_name.casefold()
        tier = existing_by_name.get(key)
        if tier is None:
            tier = SeatTier(
                show_id=show_id,
                tier_name=item.tier_name,
                price=item.price,
                total_seats=0,
                available_seats=0,
            )
            session.add(tier)
            existing_by_name[key] = tier
        else:
            tier.tier_name = item.tier_name
            tier.price = item.price
        changed_tiers.append(tier)

    session.flush()
    return changed_tiers
