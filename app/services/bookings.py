from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import BusinessError
from app.db.session import db_now
from app.models import Booking, BookingStatusHistory, Hotel, Payment, PaymentStatusHistory, Room
from app.schemas import BookingOut
from app.services import idempotency
from app.services.common import require

BLOCKING = ("pending_payment", "confirmed")


def booking_transition(db, booking, status, reason, actor_id=None):
    if booking.status == status:
        return
    db.add(
        BookingStatusHistory(
            booking_id=booking.id,
            from_status=booking.status,
            to_status=status,
            reason=reason,
            actor_id=actor_id,
        )
    )
    booking.status = status


def payment_transition(db, payment, status, reason, actor_id=None):
    if payment.status == status:
        return
    db.add(
        PaymentStatusHistory(
            payment_id=payment.id,
            from_status=payment.status,
            to_status=status,
            reason=reason,
            actor_id=actor_id,
        )
    )
    payment.status = status


def lock_room(db, room_id):
    room = require(db.get(Room, room_id))
    hotel = db.scalar(
        select(Hotel)
        .where(Hotel.id == room.hotel_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    room = db.scalar(
        select(Room)
        .where(Room.id == room_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return hotel, require(room)


def settle_room(db, room_id, now):
    bookings = list(
        db.scalars(
            select(Booking)
            .where(Booking.room_id == room_id, Booking.status.in_(BLOCKING))
            .order_by(Booking.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    for booking in bookings:
        if booking.status == "pending_payment" and now >= booking.expires_at:
            booking_transition(db, booking, "expired", "Payment hold expired")
            for payment in db.scalars(
                select(Payment)
                .where(Payment.booking_id == booking.id, Payment.status == "pending")
                .with_for_update()
            ):
                payment_transition(db, payment, "cancelled", "Booking expired")
        elif booking.status == "confirmed" and now.date() >= booking.check_out:
            booking_transition(db, booking, "completed", "Check-out date reached")
    db.flush()


def settle_selection(db, room_ids):
    # Global hotel/room ordering is also used by catalog operations.
    rows = (
        list(
            db.execute(
                select(Room.hotel_id, Room.id)
                .where(Room.id.in_(room_ids))
                .order_by(Room.hotel_id, Room.id)
            )
        )
        if room_ids
        else []
    )
    for _, room_id in rows:
        lock_room(db, room_id)
        settle_room(db, room_id, db_now(db))


def owned_booking(db, booking_id, user, *, owner_only=False):
    booking = require(db.get(Booking, booking_id))
    if booking.user_id != user.id and (owner_only or user.role != "admin"):
        raise BusinessError(404, "NOT_FOUND", "Booking not found.")
    return booking


def locked_booking(db, booking_id, user, *, owner_only=False):
    booking = owned_booking(db, booking_id, user, owner_only=owner_only)
    lock_room(db, booking.room_id)
    booking = db.scalar(
        select(Booking)
        .where(Booking.id == booking_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = db_now(db)
    settle_room(db, booking.room_id, now)
    return booking, now


def validate_stay(stay, now):
    if stay.check_in < now.date():
        raise BusinessError(422, "PAST_CHECK_IN", "Check-in cannot be in the past.", persist=True)


def overlapping(db, room_id, stay):
    return (
        db.scalar(
            select(Booking.id)
            .where(
                Booking.room_id == room_id,
                Booking.status.in_(BLOCKING),
                Booking.check_in < stay.check_out,
                Booking.check_out > stay.check_in,
            )
            .limit(1)
        )
        is not None
    )


def availability(db, room_id, stay):
    hotel, room = lock_room(db, room_id)
    if hotel.is_archived or room.is_archived:
        raise BusinessError(404, "NOT_FOUND", "Room not found.")
    now = db_now(db)
    settle_room(db, room.id, now)
    validate_stay(stay, now)
    reason = None
    if not room.is_available:
        reason = "ROOM_DISABLED"
    elif stay.guests > room.capacity:
        reason = "CAPACITY_EXCEEDED"
    elif overlapping(db, room.id, stay):
        reason = "ROOM_NOT_AVAILABLE"
    nights = (stay.check_out - stay.check_in).days
    return {
        "room_id": room.id,
        **stay.model_dump(),
        "available": reason is None,
        "reason": reason,
        "nights": nights,
        "total_price": room.price_per_night * nights,
    }


def create_booking(db, user, data, key):
    record, request_hash = idempotency.lock_and_lookup(
        db, user.id, key, data.model_dump(mode="json")
    )
    if record:
        return record.response_body, True
    hotel, room = lock_room(db, data.room_id)
    now = db_now(db)
    settle_room(db, room.id, now)
    validate_stay(data, now)
    if hotel.is_archived or room.is_archived:
        raise BusinessError(404, "NOT_FOUND", "Room not found.", persist=True)
    if not room.is_available:
        raise BusinessError(
            409, "ROOM_DISABLED", "Room does not accept new bookings.", persist=True
        )
    if data.guests > room.capacity:
        raise BusinessError(
            409, "CAPACITY_EXCEEDED", "Guest count exceeds room capacity.", persist=True
        )
    if overlapping(db, room.id, data):
        raise BusinessError(
            409, "ROOM_NOT_AVAILABLE", "Room is occupied for these dates.", persist=True
        )
    booking = Booking(
        user_id=user.id,
        room_id=room.id,
        check_in=data.check_in,
        check_out=data.check_out,
        guests=data.guests,
        status="pending_payment",
        price_per_night=room.price_per_night,
        total_price=room.price_per_night * (data.check_out - data.check_in).days,
        currency="RUB",
        expires_at=now + timedelta(minutes=get_settings().hold_minutes),
    )
    db.add(booking)
    db.flush()
    db.add(
        BookingStatusHistory(
            booking_id=booking.id,
            from_status=None,
            to_status=booking.status,
            reason="Booking created",
            actor_id=user.id,
        )
    )
    body = BookingOut.model_validate(booking).model_dump(mode="json")
    idempotency.save(db, user.id, key, request_hash, body)
    db.flush()
    return body, False


def cancel_booking(db, booking_id, user):
    booking, now = locked_booking(db, booking_id, user)
    if booking.status == "cancelled":
        return booking
    if booking.status not in BLOCKING:
        raise BusinessError(
            409,
            "BOOKING_STATE_CONFLICT",
            "Booking cannot be cancelled in its current state.",
            persist=True,
        )
    if now.date() >= booking.check_in:
        raise BusinessError(
            409,
            "CANCELLATION_CLOSED",
            "Cancellation is allowed only before the check-in date.",
            persist=True,
        )
    payments = list(
        db.scalars(
            select(Payment)
            .where(Payment.booking_id == booking.id)
            .order_by(Payment.id)
            .with_for_update()
        )
    )
    for payment in payments:
        if payment.status == "pending":
            payment_transition(db, payment, "cancelled", "Booking cancelled", user.id)
        elif payment.status == "succeeded":
            payment_transition(db, payment, "refunded", "Full simulated refund", user.id)
    booking_transition(db, booking, "cancelled", "Cancelled by user or administrator", user.id)
    db.flush()
    return booking
