from pathlib import Path
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import Booking, BookingItem, Cinema, Movie, Offer, Screen, SeatTier, Show, TaxConfig, User
from app.db.session import get_db
from app.services.booking_service import BookingService
from app.services.seat_tier_import import apply_seat_tier_import, parse_seat_tier_csv

app = FastAPI(title="Multiplex Pricing Engine")

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/")
def home_page():
    return FileResponse(BASE_DIR / "templates" / "login.html")


@app.get("/login")
def login_page():
    return FileResponse(BASE_DIR / "templates" / "login.html")


@app.get("/dashboard")
def dashboard_page():
    return FileResponse(BASE_DIR / "templates" / "dashboard.html")


@app.get("/booking")
def booking_page():
    return FileResponse(BASE_DIR / "templates" / "booking.html")


@app.get("/booking-confirmation")
def booking_confirmation_page():
    return FileResponse(BASE_DIR / "templates" / "booking_confirmation.html")


@app.get("/bookings-history")
def bookings_history_page():
    return FileResponse(BASE_DIR / "templates" / "bookings_history.html")


@app.get("/admin")
def admin_page():
    return FileResponse(BASE_DIR / "templates" / "admin.html")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/auth/login")
def login_api(payload: dict, db: Session = Depends(get_db)):
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    valid_password = user is not None and (user.password_hash == password or (user.password_hash == "demo-hash" and password == "admin123"))
    if not valid_password:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"token": f"demo-token-{user.id}", "user": {"id": user.id, "username": user.username, "role": user.role}}


@app.post("/pricing/calculate")
def calculate_pricing(payload: dict):
    from app.pricing.engine import calculate_booking_breakup

    line_items = [
        (item["tier"], item["quantity"], item["unit_price"])
        for item in payload.get("items", [])
    ]

    result = calculate_booking_breakup(
        line_items=line_items,
        festival_discount=payload.get("festival_discount", 0),
        membership_percent=payload.get("membership_percent", 0),
        membership_cap=payload.get("membership_cap", 0),
        convenience_fee_per_ticket=payload.get("convenience_fee_per_ticket", 0),
        gst_rate=payload.get("gst_rate", 0.18),
    )
    return result


def _booking_response(booking: Booking) -> dict:
    return {
        "id": booking.id,
        "reference": f"MX-{booking.id:05d}",
        "show_id": booking.show_id,
        "show": booking.show.movie.title,
        "screen": booking.show.screen.name,
        "show_datetime": booking.show.show_datetime.isoformat(),
        "status": booking.status,
        "member_id": booking.member_id,
        "items": [
            {
                "tier_name": item.tier.tier_name,
                "quantity": item.quantity,
                "price_per_seat": str(item.price_per_seat),
                "line_total": str(item.line_total),
            }
            for item in booking.booking_items
        ],
        "subtotal": str(booking.subtotal),
        "total_discount": str(booking.total_discount),
        "convenience_fee": str(booking.convenience_fee),
        "cgst": str(booking.cgst),
        "sgst": str(booking.sgst),
        "grand_total": str(booking.grand_total),
        "breakup": booking.breakup_json,
        "created_at": booking.created_at.isoformat(),
    }


def _staff_user_id(db: Session) -> int:
    user = db.execute(select(User).where(User.username == "staff")).scalar_one_or_none()
    if user is None:
        user = db.execute(select(User).order_by(User.id)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=503, detail="No staff user is configured")
    return user.id


@app.get("/api/dashboard")
def dashboard_api(show_id: int | None = None, db: Session = Depends(get_db)):
    shows = db.execute(select(Show).order_by(Show.show_datetime)).scalars().all()
    bookings = db.execute(select(Booking).where(Booking.status == "CONFIRMED")).scalars().all()
    sold_tickets = sum(item.quantity for booking in bookings for item in booking.booking_items)
    revenue = sum((booking.grand_total for booking in bookings), Decimal("0.00"))
    tiers = db.execute(select(SeatTier).where(SeatTier.show_id == (show_id or (shows[0].id if shows else 0)))).scalars().all()
    selected_show = next((show for show in shows if show.id == (show_id or (shows[0].id if shows else 0))), None)
    return {
        "stats": {
            "shows": len(shows),
            "tickets_sold": sold_tickets,
            "revenue": str(revenue),
            "sold_out_tiers": sum(1 for tier in tiers if tier.available_seats == 0),
        },
        "shows": [
            {
                "id": show.id,
                "title": show.movie.title,
                "screen": show.screen.name,
                "show_datetime": show.show_datetime.isoformat(),
            }
            for show in shows
        ],
        "availability": [
            {"tier_name": tier.tier_name, "available_seats": tier.available_seats, "total_seats": tier.total_seats}
            for tier in tiers
        ],
        "selected_show_id": selected_show.id if selected_show else None,
    }


@app.get("/api/shows/{show_id}")
def show_api(show_id: int, db: Session = Depends(get_db)):
    show = db.get(Show, show_id)
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")
    return {
        "id": show.id,
        "title": show.movie.title,
        "screen": show.screen.name,
        "show_datetime": show.show_datetime.isoformat(),
        "tiers": [
            {"tier_name": tier.tier_name, "price": str(tier.price), "available_seats": tier.available_seats, "total_seats": tier.total_seats}
            for tier in show.seat_tiers
        ],
        "tax": {"convenience_fee_per_ticket": str(show.tax_config.convenience_fee_per_ticket), "gst_rate": str(show.tax_config.cgst_rate + show.tax_config.sgst_rate)},
    }


@app.post("/api/bookings")
def create_booking_api(payload: dict, db: Session = Depends(get_db)):
    try:
        service = BookingService(db)
        booking = service.create_booking(
            show_id=int(payload.get("show_id")),
            created_by_user_id=_staff_user_id(db),
            member_id=payload.get("member_id") or None,
            requested_items=payload.get("items", []),
            festival_discount=Decimal(str(payload.get("festival_discount", "0"))),
            membership_percent=Decimal(str(payload.get("membership_percent", "0"))),
            membership_cap=Decimal(str(payload.get("membership_cap", "0"))),
        )
        db.commit()
        return _booking_response(booking)
    except (ValueError, InvalidOperation, TypeError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@app.get("/api/bookings")
def bookings_api(db: Session = Depends(get_db)):
    bookings = db.execute(select(Booking).order_by(desc(Booking.created_at))).scalars().all()
    return {"bookings": [_booking_response(booking) for booking in bookings]}


@app.get("/api/bookings/{booking_id}")
def booking_api(booking_id: int, db: Session = Depends(get_db)):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return _booking_response(booking)


@app.put("/api/admin/shows/{show_id}")
def update_show_api(show_id: int, payload: dict, db: Session = Depends(get_db)):
    show = db.get(Show, show_id)
    if show is None:
        raise HTTPException(status_code=404, detail="Show not found")
    try:
        show.movie.title = str(payload.get("movie_title", show.movie.title)).strip() or show.movie.title
        show.screen.name = str(payload.get("screen_name", show.screen.name)).strip() or show.screen.name
        show.screen.cinema.name = str(payload.get("cinema_name", show.screen.cinema.name)).strip() or show.screen.cinema.name
        if payload.get("show_datetime"):
            show.show_datetime = datetime.fromisoformat(payload["show_datetime"])
        db.commit()
        return {"message": "Show saved", "show": {"id": show.id, "title": show.movie.title, "screen": show.screen.name, "show_datetime": show.show_datetime.isoformat()}}
    except (ValueError, TypeError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Show time must be a valid date and time") from exc


@app.put("/api/admin/shows/{show_id}/tiers")
def update_tiers_api(show_id: int, payload: dict, db: Session = Depends(get_db)):
    if db.get(Show, show_id) is None:
        raise HTTPException(status_code=404, detail="Show not found")
    try:
        existing = {tier.tier_name.casefold(): tier for tier in db.execute(select(SeatTier).where(SeatTier.show_id == show_id)).scalars().all()}
        updated = []
        for item in payload.get("tiers", []):
            name = " ".join(str(item.get("tier_name", "")).split()).title()
            price = Decimal(str(item.get("price")))
            if not name or price < 0:
                raise ValueError("Tier name is required and price cannot be negative")
            tier = existing.get(name.casefold())
            if tier is None:
                tier = SeatTier(show_id=show_id, tier_name=name, price=price, total_seats=0, available_seats=0)
                db.add(tier)
            else:
                tier.tier_name, tier.price = name, price
            updated.append({"tier_name": name, "price": str(price)})
        db.commit()
        return {"message": "Tier prices updated", "tiers": updated}
    except (ValueError, InvalidOperation, TypeError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/admin/offers")
def update_offers_api(payload: dict, db: Session = Depends(get_db)):
    try:
        values = {
            "Festival discount": ("FLAT", Decimal(str(payload.get("festival_discount", "0"))), None, None),
            "Membership discount": ("PERCENT", None, Decimal(str(payload.get("membership_percent", "0"))), Decimal(str(payload.get("membership_cap", "0")))),
        }
        for name, (offer_type, flat, percent, cap) in values.items():
            offer = db.execute(select(Offer).where(Offer.name == name)).scalar_one_or_none()
            if offer is None:
                offer = Offer(name=name, offer_type=offer_type, is_active=True, requires_membership=name.startswith("Membership"))
                db.add(offer)
            offer.offer_type, offer.flat_amount, offer.percent_value, offer.cap_amount = offer_type, flat, percent, cap
        db.commit()
        return {"message": "Offers saved"}
    except (ValueError, InvalidOperation, TypeError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Offer values must be valid numbers") from exc


@app.post("/api/admin/shows/{show_id}/seat-tiers/import/preview")
async def preview_seat_tier_import(show_id: int, file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")
    try:
        content = (await file.read()).decode("utf-8-sig")
        report = parse_seat_tier_csv(content)
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"show_id": show_id, **report.as_dict()}


@app.post("/api/admin/shows/{show_id}/seat-tiers/import/apply")
async def apply_seat_tier_import_api(
    show_id: int,
    file: UploadFile = File(...),
    confirm: bool = Query(False),
    db: Session = Depends(get_db),
):
    if not confirm:
        raise HTTPException(status_code=400, detail="Confirmation is required before applying the import")
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file")
    try:
        content = (await file.read()).decode("utf-8-sig")
        report = parse_seat_tier_csv(content)
        changed_tiers = apply_seat_tier_import(db, show_id, report)
        db.commit()
    except UnicodeDecodeError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return {
        "show_id": show_id,
        "updated_count": len(changed_tiers),
        "tiers": [{"tier_name": tier.tier_name, "price": str(tier.price)} for tier in changed_tiers],
    }
