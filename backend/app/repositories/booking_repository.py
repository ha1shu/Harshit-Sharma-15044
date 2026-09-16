from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Booking, BookingItem, Offer, SeatTier, Show, User


class BookingRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_show(self, show_id: int) -> Show | None:
        return self.session.get(Show, show_id)

    def get_seat_tier(self, show_id: int, tier_name: str) -> SeatTier | None:
        stmt = select(SeatTier).where(SeatTier.show_id == show_id, SeatTier.tier_name == tier_name)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_active_offers(self) -> list[Offer]:
        stmt = select(Offer).where(Offer.is_active.is_(True))
        return self.session.execute(stmt).scalars().all()

    def get_user(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        return self.session.execute(stmt).scalar_one_or_none()

    def create_booking(self, booking: Booking) -> Booking:
        self.session.add(booking)
        self.session.flush()
        return booking

    def create_booking_item(self, booking_item: BookingItem) -> BookingItem:
        self.session.add(booking_item)
        self.session.flush()
        return booking_item

    def get_booking_by_id(self, booking_id: int) -> Booking | None:
        return self.session.get(Booking, booking_id)

    def list_bookings(self, **filters: Any) -> list[Booking]:
        stmt = select(Booking)
        for field_name, value in filters.items():
            if value is not None:
                stmt = stmt.where(getattr(Booking, field_name) == value)
        return self.session.execute(stmt).scalars().all()
