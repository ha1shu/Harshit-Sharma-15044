from __future__ import annotations

from decimal import Decimal
from datetime import datetime

from sqlalchemy import select

from app.db.config import settings
from app.db.models import Cinema, Movie, SeatTier, Show, TaxConfig, User
from app.db.session import SessionLocal


def seed_demo_data() -> None:
    session = SessionLocal()
    try:
        if session.execute(select(User).limit(1)).first():
            return

        cinema = Cinema(name="Aurora Multiplex", city="Bengaluru")
        movie = Movie(title="Midnight Echo", duration_minutes=142, language="English")
        tax_config = TaxConfig(
            name="Standard GST",
            cgst_rate=Decimal("9.00"),
            sgst_rate=Decimal("9.00"),
            igst_rate=None,
            convenience_fee_per_ticket=Decimal("20.00"),
            fee_is_taxable=True,
        )
        session.add_all([cinema, movie, tax_config])
        session.flush()

        screen = session.execute(select(Cinema).where(Cinema.id == cinema.id)).scalar_one()
        _ = screen
        from app.db.models import Screen

        screen = Screen(cinema_id=cinema.id, name="Screen 1")
        session.add(screen)
        session.flush()

        show = Show(movie_id=movie.id, screen_id=screen.id, show_datetime=datetime.utcnow(), tax_config_id=tax_config.id)
        session.add(show)
        session.flush()

        session.add_all(
            [
                SeatTier(show_id=show.id, tier_name="Silver", price=Decimal("200.00"), total_seats=100, available_seats=100),
                SeatTier(show_id=show.id, tier_name="Gold", price=Decimal("350.00"), total_seats=80, available_seats=80),
                SeatTier(show_id=show.id, tier_name="Platinum", price=Decimal("500.00"), total_seats=50, available_seats=50),
            ]
        )
        session.add(User(username="admin", password_hash="demo-hash", role="ADMIN"))
        session.add(User(username="staff", password_hash="demo-hash", role="STAFF"))
        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    seed_demo_data()
