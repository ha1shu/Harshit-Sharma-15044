from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class Cinema(Base):
    __tablename__ = "cinemas"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    city = Column(String(255), nullable=False)

    screens = relationship("Screen", back_populates="cinema")


class Screen(Base):
    __tablename__ = "screens"

    id = Column(Integer, primary_key=True, index=True)
    cinema_id = Column(Integer, ForeignKey("cinemas.id"), nullable=False)
    name = Column(String(255), nullable=False)

    cinema = relationship("Cinema", back_populates="screens")
    shows = relationship("Show", back_populates="screen")

    __table_args__ = (Index("ix_screens_cinema_id", "cinema_id"),)


class Movie(Base):
    __tablename__ = "movies"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    language = Column(String(100), nullable=False)

    shows = relationship("Show", back_populates="movie")


class TaxConfig(Base):
    __tablename__ = "tax_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    cgst_rate = Column(Numeric(5, 2), nullable=False)
    sgst_rate = Column(Numeric(5, 2), nullable=False)
    igst_rate = Column(Numeric(5, 2), nullable=True)
    convenience_fee_per_ticket = Column(Numeric(10, 2), nullable=False)
    fee_is_taxable = Column(Boolean, default=True, nullable=False)

    shows = relationship("Show", back_populates="tax_config")


class Show(Base):
    __tablename__ = "shows"

    id = Column(Integer, primary_key=True, index=True)
    screen_id = Column(Integer, ForeignKey("screens.id"), nullable=False)
    movie_id = Column(Integer, ForeignKey("movies.id"), nullable=False)
    show_datetime = Column(DateTime, nullable=False)
    tax_config_id = Column(Integer, ForeignKey("tax_configs.id"), nullable=False)

    screen = relationship("Screen", back_populates="shows")
    movie = relationship("Movie", back_populates="shows")
    tax_config = relationship("TaxConfig", back_populates="shows")
    seat_tiers = relationship("SeatTier", back_populates="show")
    bookings = relationship("Booking", back_populates="show")

    __table_args__ = (
        Index("ix_shows_screen_id", "screen_id"),
        Index("ix_shows_show_datetime", "show_datetime"),
    )


class SeatTier(Base):
    __tablename__ = "seat_tiers"

    id = Column(Integer, primary_key=True, index=True)
    show_id = Column(Integer, ForeignKey("shows.id"), nullable=False)
    tier_name = Column(String(100), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    total_seats = Column(Integer, nullable=False)
    available_seats = Column(Integer, nullable=False)

    show = relationship("Show", back_populates="seat_tiers")
    booking_items = relationship("BookingItem", back_populates="tier")

    __table_args__ = (
        UniqueConstraint("show_id", "tier_name", name="uq_show_tier_name"),
        CheckConstraint("available_seats >= 0 AND available_seats <= total_seats", name="ck_available_seats_range"),
        Index("ix_seat_tiers_show_id", "show_id"),
    )


class Offer(Base):
    __tablename__ = "offers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    offer_type = Column(Enum("FLAT", "PERCENT", name="offer_type_enum"), nullable=False)
    flat_amount = Column(Numeric(10, 2), nullable=True)
    percent_value = Column(Numeric(5, 2), nullable=True)
    cap_amount = Column(Numeric(10, 2), nullable=True)
    active_from = Column(Date, nullable=True)
    active_to = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    requires_membership = Column(Boolean, default=False, nullable=False)

    booking_offers = relationship("BookingOffer", back_populates="offer")

    __table_args__ = (Index("ix_offers_active_period", "is_active", "active_from", "active_to"),)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum("ADMIN", "STAFF", name="user_role_enum"), nullable=False)

    bookings = relationship("Booking", back_populates="created_by_user")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    show_id = Column(Integer, ForeignKey("shows.id"), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    member_id = Column(String(100), nullable=True)
    status = Column(String(50), default="CONFIRMED", nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)
    total_discount = Column(Numeric(10, 2), nullable=False)
    convenience_fee = Column(Numeric(10, 2), nullable=False)
    cgst = Column(Numeric(10, 2), nullable=False)
    sgst = Column(Numeric(10, 2), nullable=False)
    grand_total = Column(Numeric(10, 2), nullable=False)
    breakup_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    show = relationship("Show", back_populates="bookings")
    created_by_user = relationship("User", back_populates="bookings")
    booking_items = relationship("BookingItem", back_populates="booking")
    booking_offers = relationship("BookingOffer", back_populates="booking")

    __table_args__ = (
        Index("ix_bookings_show_id", "show_id"),
        Index("ix_bookings_created_at", "created_at"),
    )


class BookingItem(Base):
    __tablename__ = "booking_items"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    tier_id = Column(Integer, ForeignKey("seat_tiers.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    price_per_seat = Column(Numeric(10, 2), nullable=False)
    line_total = Column(Numeric(10, 2), nullable=False)

    booking = relationship("Booking", back_populates="booking_items")
    tier = relationship("SeatTier", back_populates="booking_items")


class BookingOffer(Base):
    __tablename__ = "booking_offers"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    offer_id = Column(Integer, ForeignKey("offers.id"), nullable=False)
    applied_amount = Column(Numeric(10, 2), nullable=False)

    booking = relationship("Booking", back_populates="booking_offers")
    offer = relationship("Offer", back_populates="booking_offers")
