import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Identified:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.clock_timestamp()
    )


class User(Identified, Timestamped, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(25))
    role: Mapped[str] = mapped_column(String(10), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint("role IN ('user', 'admin')", name="ck_user_role"),
    )


class Hotel(Identified, Timestamped, Base):
    __tablename__ = "hotels"
    name: Mapped[str] = mapped_column(String(150))
    city: Mapped[str] = mapped_column(String(100), index=True)
    address: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(Text, default="")
    rating: Mapped[Decimal] = mapped_column(Numeric(2, 1))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (CheckConstraint("rating BETWEEN 0 AND 5", name="ck_hotel_rating"),)


class Room(Identified, Timestamped, Base):
    __tablename__ = "rooms"
    hotel_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hotels.id"), index=True)
    room_number: Mapped[str] = mapped_column(String(20))
    type: Mapped[str] = mapped_column(String(20))
    capacity: Mapped[int] = mapped_column(Integer)
    price_per_night: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("hotel_id", "room_number", name="uq_room_number"),
        CheckConstraint("capacity BETWEEN 1 AND 10", name="ck_room_capacity"),
        CheckConstraint("price_per_night > 0", name="ck_room_price"),
        CheckConstraint(
            "type IN ('single', 'double', 'twin', 'family', 'suite')", name="ck_room_type"
        ),
    )


class Booking(Identified, Timestamped, Base):
    __tablename__ = "bookings"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True)
    check_in: Mapped[date] = mapped_column(Date)
    check_out: Mapped[date] = mapped_column(Date)
    guests: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(25), index=True)
    price_per_night: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    __table_args__ = (
        CheckConstraint("check_out - check_in BETWEEN 1 AND 14", name="ck_booking_nights"),
        CheckConstraint("guests BETWEEN 1 AND 10", name="ck_booking_guests"),
        CheckConstraint(
            "price_per_night > 0 AND total_price = price_per_night * (check_out - check_in)",
            name="ck_booking_total",
        ),
        CheckConstraint("currency = 'RUB'", name="ck_booking_currency"),
        CheckConstraint(
            "status IN ('pending_payment','confirmed','cancelled','expired','completed')",
            name="ck_booking_status",
        ),
        ExcludeConstraint(
            ("room_id", "="),
            (func.daterange(check_in, check_out, "[)"), "&&"),
            where=text("status IN ('pending_payment','confirmed')"),
            using="gist",
            name="no_overlapping_bookings",
        ),
    )


class Payment(Identified, Timestamped, Base):
    __tablename__ = "payments"
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    status: Mapped[str] = mapped_column(String(15))
    failure_reason: Mapped[str | None] = mapped_column(String(250))
    __table_args__ = (
        CheckConstraint("amount > 0 AND currency = 'RUB'", name="ck_payment_amount"),
        CheckConstraint(
            "status IN ('pending','succeeded','failed','cancelled','refunded')",
            name="ck_payment_status",
        ),
        Index(
            "uq_payment_pending",
            "booking_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "uq_payment_charged",
            "booking_id",
            unique=True,
            postgresql_where=text("status IN ('succeeded','refunded')"),
        ),
    )


class IdempotencyRecord(Identified, Base):
    __tablename__ = "idempotency_records"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    operation: Mapped[str] = mapped_column(String(50))
    key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int] = mapped_column(Integer)
    response_body: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("user_id", "operation", "key", name="uq_idempotency"),)


class History(Identified):
    from_status: Mapped[str | None] = mapped_column(String(25))
    to_status: Mapped[str] = mapped_column(String(25))
    reason: Mapped[str] = mapped_column(String(250))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )


class BookingStatusHistory(History, Base):
    __tablename__ = "booking_status_history"
    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"), index=True)


class PaymentStatusHistory(History, Base):
    __tablename__ = "payment_status_history"
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.id"), index=True)
