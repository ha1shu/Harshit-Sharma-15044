"""initial schema

Revision ID: 20260916_initial
Revises: 
Create Date: 2026-09-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "20260916_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cinemas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cinemas_id"), "cinemas", ["id"], unique=False)

    op.create_table(
        "screens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cinema_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["cinema_id"], ["cinemas.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_screens_id"), "screens", ["id"], unique=False)
    op.create_index("ix_screens_cinema_id", "screens", ["cinema_id"], unique=False)

    op.create_table(
        "movies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_movies_id"), "movies", ["id"], unique=False)

    op.create_table(
        "tax_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("cgst_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("sgst_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("igst_rate", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("convenience_fee_per_ticket", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("fee_is_taxable", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tax_configs_id"), "tax_configs", ["id"], unique=False)

    op.create_table(
        "shows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("screen_id", sa.Integer(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("show_datetime", sa.DateTime(), nullable=False),
        sa.Column("tax_config_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"]),
        sa.ForeignKeyConstraint(["screen_id"], ["screens.id"]),
        sa.ForeignKeyConstraint(["tax_config_id"], ["tax_configs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_shows_id"), "shows", ["id"], unique=False)
    op.create_index("ix_shows_screen_id", "shows", ["screen_id"], unique=False)
    op.create_index("ix_shows_show_datetime", "shows", ["show_datetime"], unique=False)

    op.create_table(
        "seat_tiers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("show_id", sa.Integer(), nullable=False),
        sa.Column("tier_name", sa.String(length=100), nullable=False),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("total_seats", sa.Integer(), nullable=False),
        sa.Column("available_seats", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["show_id"], ["shows.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("show_id", "tier_name", name="uq_show_tier_name"),
        sa.CheckConstraint("available_seats >= 0 AND available_seats <= total_seats", name="ck_available_seats_range"),
    )
    op.create_index(op.f("ix_seat_tiers_id"), "seat_tiers", ["id"], unique=False)
    op.create_index("ix_seat_tiers_show_id", "seat_tiers", ["show_id"], unique=False)

    op.create_table(
        "offers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("offer_type", sa.Enum("FLAT", "PERCENT", name="offer_type_enum"), nullable=False),
        sa.Column("flat_amount", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("percent_value", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("cap_amount", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("active_from", sa.Date(), nullable=True),
        sa.Column("active_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("requires_membership", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_offers_id"), "offers", ["id"], unique=False)
    op.create_index("ix_offers_active_period", "offers", ["is_active", "active_from", "active_to"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.Enum("ADMIN", "STAFF", name="user_role_enum"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)

    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("show_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("total_discount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("convenience_fee", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("cgst", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("sgst", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("grand_total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("breakup_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["show_id"], ["shows.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bookings_id"), "bookings", ["id"], unique=False)
    op.create_index("ix_bookings_show_id", "bookings", ["show_id"], unique=False)
    op.create_index("ix_bookings_created_at", "bookings", ["created_at"], unique=False)

    op.create_table(
        "booking_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("tier_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price_per_seat", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
        sa.ForeignKeyConstraint(["tier_id"], ["seat_tiers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_booking_items_id"), "booking_items", ["id"], unique=False)

    op.create_table(
        "booking_offers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("booking_id", sa.Integer(), nullable=False),
        sa.Column("offer_id", sa.Integer(), nullable=False),
        sa.Column("applied_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_booking_offers_id"), "booking_offers", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_booking_offers_id"), table_name="booking_offers")
    op.drop_table("booking_offers")
    op.drop_index(op.f("ix_booking_items_id"), table_name="booking_items")
    op.drop_table("booking_items")
    op.drop_index("ix_bookings_created_at", table_name="bookings")
    op.drop_index("ix_bookings_show_id", table_name="bookings")
    op.drop_index(op.f("ix_bookings_id"), table_name="bookings")
    op.drop_table("bookings")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
    op.drop_index("ix_offers_active_period", table_name="offers")
    op.drop_index(op.f("ix_offers_id"), table_name="offers")
    op.drop_table("offers")
    op.drop_index("ix_seat_tiers_show_id", table_name="seat_tiers")
    op.drop_index(op.f("ix_seat_tiers_id"), table_name="seat_tiers")
    op.drop_table("seat_tiers")
    op.drop_index("ix_shows_show_datetime", table_name="shows")
    op.drop_index("ix_shows_screen_id", table_name="shows")
    op.drop_index(op.f("ix_shows_id"), table_name="shows")
    op.drop_table("shows")
    op.drop_index(op.f("ix_tax_configs_id"), table_name="tax_configs")
    op.drop_table("tax_configs")
    op.drop_index(op.f("ix_movies_id"), table_name="movies")
    op.drop_table("movies")
    op.drop_index("ix_screens_cinema_id", table_name="screens")
    op.drop_index(op.f("ix_screens_id"), table_name="screens")
    op.drop_table("screens")
    op.drop_index(op.f("ix_cinemas_id"), table_name="cinemas")
    op.drop_table("cinemas")
