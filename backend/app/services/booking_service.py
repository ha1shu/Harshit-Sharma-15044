from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Booking, BookingItem, SeatTier, Show
from app.pricing.engine import calculate_booking_breakup


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


class BookingService:
    def __init__(self, session: Session):
        self.session = session

    def reserve_seats(self, show_id: int, tier_name: str, quantity: int) -> SeatTier:
        stmt = (
            select(SeatTier)
            .where(SeatTier.show_id == show_id, SeatTier.tier_name == tier_name)
            .with_for_update()
        )
        tier = self.session.execute(stmt).scalar_one()
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero")
        if tier.available_seats < quantity:
            raise ValueError("Not enough seats available")
        tier.available_seats -= quantity
        self.session.flush()
        return tier

    def create_booking_from_pricing(
        self,
        *,
        show_id: int,
        created_by_user_id: int,
        member_id: str | None,
        line_items: list[tuple[str, int, Decimal]],
        festival_discount: Decimal = Decimal("0.00"),
        membership_percent: Decimal = Decimal("0.00"),
        membership_cap: Decimal = Decimal("0.00"),
        convenience_fee_per_ticket: Decimal = Decimal("0.00"),
        gst_rate: Decimal = Decimal("0.18"),
    ) -> Booking:
        pricing = calculate_booking_breakup(
            line_items=line_items,
            festival_discount=festival_discount,
            membership_percent=membership_percent,
            membership_cap=membership_cap,
            convenience_fee_per_ticket=convenience_fee_per_ticket,
            gst_rate=gst_rate,
        )

        booking = Booking(
            show_id=show_id,
            created_by_user_id=created_by_user_id,
            member_id=member_id,
            status="CONFIRMED",
            subtotal=pricing["subtotal"],
            total_discount=pricing["flat_discount"] + pricing["membership_discount"],
            convenience_fee=pricing["convenience_fee"],
            cgst=pricing["cgst"],
            sgst=pricing["sgst"],
            grand_total=pricing["grand_total"],
            breakup_json=_json_safe(pricing),
            created_at=datetime.utcnow(),
        )
        self.session.add(booking)
        self.session.flush()

        for tier_name, quantity, price in line_items:
            tier = self.reserve_seats(show_id, tier_name, quantity)
            item = BookingItem(
                booking_id=booking.id,
                tier_id=tier.id,
                quantity=quantity,
                price_per_seat=price,
                line_total=Decimal(str(quantity)) * price,
            )
            self.session.add(item)

        self.session.flush()
        return booking

    def create_booking(
        self,
        *,
        show_id: int,
        created_by_user_id: int,
        member_id: str | None,
        requested_items: list[dict],
        festival_discount: Decimal = Decimal("0.00"),
        membership_percent: Decimal = Decimal("0.00"),
        membership_cap: Decimal = Decimal("0.00"),
    ) -> Booking:
        if not requested_items:
            raise ValueError("Select at least one seat")
        if self.session.get(Show, show_id) is None:
            raise ValueError(f"Show {show_id} does not exist")

        quantities: dict[str, int] = {}
        for item in requested_items:
            tier_name = str(item.get("tier_name", "")).strip()
            quantity = int(item.get("quantity", 0))
            if not tier_name or quantity <= 0:
                raise ValueError("Each booking item needs a tier and a positive quantity")
            quantities[tier_name.casefold()] = quantities.get(tier_name.casefold(), 0) + quantity

        locked_tiers = {}
        for tier_name_key in sorted(quantities):
            stmt = (
                select(SeatTier)
                .where(SeatTier.show_id == show_id, SeatTier.tier_name.ilike(tier_name_key))
                .with_for_update()
            )
            tier = self.session.execute(stmt).scalar_one_or_none()
            if tier is None:
                raise ValueError(f"Seat tier '{tier_name_key}' does not exist for this show")
            quantity = quantities[tier_name_key]
            if tier.available_seats < quantity:
                raise ValueError(f"Only {tier.available_seats} {tier.tier_name} seat(s) remain")
            locked_tiers[tier_name_key] = tier

        line_items = [
            (tier.tier_name, quantities[tier_name_key], Decimal(str(tier.price)))
            for tier_name_key, tier in locked_tiers.items()
        ]
        show = self.session.get(Show, show_id)
        tax_config = show.tax_config
        gst_rate = Decimal(str(tax_config.cgst_rate + tax_config.sgst_rate)) / Decimal("100")
        pricing = calculate_booking_breakup(
            line_items=line_items,
            festival_discount=festival_discount,
            membership_percent=membership_percent,
            membership_cap=membership_cap,
            convenience_fee_per_ticket=Decimal(str(tax_config.convenience_fee_per_ticket)),
            gst_rate=gst_rate,
        )

        booking = Booking(
            show_id=show_id,
            created_by_user_id=created_by_user_id,
            member_id=member_id,
            status="CONFIRMED",
            subtotal=pricing["subtotal"],
            total_discount=pricing["flat_discount"] + pricing["membership_discount"],
            convenience_fee=pricing["convenience_fee"],
            cgst=pricing["cgst"],
            sgst=pricing["sgst"],
            grand_total=pricing["grand_total"],
            breakup_json=_json_safe(pricing),
            created_at=datetime.utcnow(),
        )
        self.session.add(booking)
        self.session.flush()

        for tier_name_key, tier in locked_tiers.items():
            quantity = quantities[tier_name_key]
            tier.available_seats -= quantity
            self.session.add(
                BookingItem(
                    booking_id=booking.id,
                    tier_id=tier.id,
                    quantity=quantity,
                    price_per_seat=tier.price,
                    line_total=Decimal(str(quantity)) * Decimal(str(tier.price)),
                )
            )

        self.session.flush()
        return booking
