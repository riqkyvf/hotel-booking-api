from sqlalchemy import select

from app.core.errors import BusinessError
from app.models import Payment, PaymentStatusHistory
from app.services.bookings import booking_transition, locked_booking, payment_transition
from app.services.common import require


def require_payable(booking):
    if booking.status == "expired":
        raise BusinessError(
            409, "BOOKING_EXPIRED", "Payment deadline has been reached.", persist=True
        )
    if booking.status != "pending_payment":
        raise BusinessError(
            409, "BOOKING_NOT_PAYABLE", "Booking is not awaiting payment.", persist=True
        )


def create_payment(db, booking_id, user):
    booking, _ = locked_booking(db, booking_id, user, owner_only=True)
    require_payable(booking)
    if db.scalar(
        select(Payment.id).where(Payment.booking_id == booking.id, Payment.status == "pending")
    ):
        raise BusinessError(
            409, "PAYMENT_ALREADY_PENDING", "An unfinished payment already exists.", persist=True
        )
    payment = Payment(
        booking_id=booking.id,
        amount=booking.total_price,
        currency=booking.currency,
        status="pending",
    )
    db.add(payment)
    db.flush()
    db.add(
        PaymentStatusHistory(
            payment_id=payment.id,
            from_status=None,
            to_status="pending",
            reason="Payment created",
            actor_id=user.id,
        )
    )
    return payment


def locked_payment(db, payment_id, user, *, owner_only=False):
    payment = require(db.get(Payment, payment_id))
    booking, now = locked_booking(db, payment.booking_id, user, owner_only=owner_only)
    payment = db.scalar(
        select(Payment)
        .where(Payment.id == payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return payment, booking, now


def simulate(db, payment_id, user, success, reason=None):
    payment, booking, _ = locked_payment(db, payment_id, user, owner_only=True)
    # Deadline and booking state take precedence over payment state.
    require_payable(booking)
    if payment.status != "pending":
        raise BusinessError(
            409, "PAYMENT_STATE_CONFLICT", "Only a pending payment may be simulated.", persist=True
        )
    if success:
        payment_transition(db, payment, "succeeded", "Simulated payment success", user.id)
        booking_transition(db, booking, "confirmed", "Payment succeeded", user.id)
    else:
        payment.failure_reason = reason
        payment_transition(db, payment, "failed", reason, user.id)
    db.flush()
    return payment
