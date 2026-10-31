"""Atomic, repeatable demo data initialization; never overwrites existing data."""

from datetime import timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal, db_now
from app.models import (
    Booking,
    BookingStatusHistory,
    Hotel,
    Payment,
    PaymentStatusHistory,
    Room,
    User,
)


def demo_id(name):
    return uuid5(NAMESPACE_URL, f"hotel-booking-demo/{name}")


def seed():
    with SessionLocal.begin() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(8173409202)"))
        if db.get(User, demo_id("admin")):
            print("Seed already applied; existing data preserved.")
            return
        now = db_now(db)
        password_hash = hash_password(get_settings().seed_password)
        for handle, role, active in [
            ("admin", "admin", True),
            ("admin2", "admin", True),
            ("alice", "user", True),
            ("bob", "user", True),
            ("disabled", "user", False),
        ]:
            db.add(
                User(
                    id=demo_id(handle),
                    email=f"{handle}@example.com",
                    password_hash=password_hash,
                    name=handle.title(),
                    phone=None,
                    role=role,
                    is_active=active,
                )
            )
        db.flush()
        locations = [
            ("Baikal Residence", "Irkutsk"),
            ("Capital Park", "Moscow"),
            ("Neva House", "Saint Petersburg"),
            ("Volga Stay", "Kazan"),
            ("Sea Breeze", "Sochi"),
        ]
        types = ["single", "double", "twin", "family", "suite"]
        capacities = [1, 2, 2, 4, 6]
        for h, (name, city) in enumerate(locations):
            hotel = Hotel(
                id=demo_id(f"hotel-{h}"),
                name=name,
                city=city,
                address=f"{h + 1} Central Street",
                description=f"Demo hotel in {city}.",
                rating=Decimal("3.0") + Decimal(h) / 2,
                is_archived=False,
            )
            db.add(hotel)
            db.flush()
            for r in range(5):
                db.add(
                    Room(
                        id=demo_id(f"room-{h}-{r}"),
                        hotel_id=hotel.id,
                        room_number=str(101 + r),
                        type=types[r],
                        capacity=capacities[r],
                        price_per_night=Decimal(1500 + h * 700 + r * 1000),
                        is_available=(h, r) != (4, 4),
                        is_archived=False,
                    )
                )
        db.flush()
        specs = [
            ("pending", 0, 0, "alice", "pending_payment", 2, 4, None),
            ("confirmed", 0, 1, "alice", "confirmed", 3, 5, "succeeded"),
            ("cancelled", 0, 2, "bob", "cancelled", 4, 6, "refunded"),
            ("expired", 0, 3, "bob", "expired", 5, 7, "cancelled"),
            ("completed", 0, 4, "alice", "completed", -5, -3, "succeeded"),
            ("declined", 1, 0, "alice", "pending_payment", 7, 8, "failed"),
            ("awaiting", 1, 1, "bob", "pending_payment", 8, 10, "pending"),
            ("inactive-owner", 1, 2, "disabled", "confirmed", 9, 11, "succeeded"),
        ]
        for name, h, r, owner, state, start, end, pay_state in specs:
            room = db.get(Room, demo_id(f"room-{h}-{r}"))
            created = (
                now - timedelta(minutes=5)
                if state == "pending_payment"
                else now - timedelta(days=8)
            )
            expires = created + timedelta(minutes=get_settings().hold_minutes)
            booking = Booking(
                id=demo_id(f"booking-{name}"),
                user_id=demo_id(owner),
                room_id=room.id,
                check_in=now.date() + timedelta(days=start),
                check_out=now.date() + timedelta(days=end),
                guests=1,
                status=state,
                price_per_night=room.price_per_night,
                total_price=room.price_per_night * (end - start),
                currency="RUB",
                expires_at=expires,
                created_at=created,
                updated_at=created,
            )
            db.add(booking)
            db.flush()
            transitions = [(None, "pending_payment", created)]
            if state in {"confirmed", "completed"} or pay_state == "refunded":
                transitions.append(("pending_payment", "confirmed", created + timedelta(minutes=1)))
            if state == "cancelled":
                transitions.append(("confirmed", "cancelled", created + timedelta(minutes=2)))
            elif state == "expired":
                transitions.append(("pending_payment", "expired", expires))
            elif state == "completed":
                transitions.append(("confirmed", "completed", now - timedelta(days=3)))
            for before, after, at in transitions:
                db.add(
                    BookingStatusHistory(
                        booking_id=booking.id,
                        from_status=before,
                        to_status=after,
                        reason="Demo seed",
                        actor_id=demo_id(owner) if after not in {"expired", "completed"} else None,
                        created_at=at,
                    )
                )
            booking.updated_at = transitions[-1][2]
            if pay_state:
                payment = Payment(
                    id=demo_id(f"payment-{name}"),
                    booking_id=booking.id,
                    amount=booking.total_price,
                    currency="RUB",
                    status=pay_state,
                    failure_reason="Simulated decline" if pay_state == "failed" else None,
                    created_at=created,
                    updated_at=created,
                )
                db.add(payment)
                db.flush()
                pay_transitions = [(None, "pending", created)]
                if pay_state == "refunded":
                    pay_transitions += [
                        ("pending", "succeeded", created + timedelta(minutes=1)),
                        ("succeeded", "refunded", created + timedelta(minutes=2)),
                    ]
                elif pay_state != "pending":
                    pay_transitions += [
                        (
                            "pending",
                            pay_state,
                            expires if pay_state == "cancelled" else created + timedelta(minutes=1),
                        )
                    ]
                for before, after, at in pay_transitions:
                    db.add(
                        PaymentStatusHistory(
                            payment_id=payment.id,
                            from_status=before,
                            to_status=after,
                            reason="Demo seed",
                            actor_id=None if after == "cancelled" else demo_id(owner),
                            created_at=at,
                        )
                    )
                payment.updated_at = pay_transitions[-1][2]
        print("Seed created: 5 users, 5 hotels, 25 rooms, 8 bookings, 7 payments.")


if __name__ == "__main__":
    seed()
