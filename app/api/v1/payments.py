from uuid import UUID

from fastapi import APIRouter

from app.api.dependencies import DB, CurrentUser
from app.schemas import FailureInput, PaymentOut
from app.services import payments

router = APIRouter(tags=["Simulated payments"])


@router.post("/bookings/{booking_id}/payments", response_model=PaymentOut, status_code=201)
def create_payment(booking_id: UUID, db: DB, user: CurrentUser):
    return payments.create_payment(db, booking_id, user)


@router.get("/payments/{payment_id}", response_model=PaymentOut)
def get_payment(payment_id: UUID, db: DB, user: CurrentUser):
    payment, _, _ = payments.locked_payment(db, payment_id, user)
    return payment


@router.post("/payments/{payment_id}/simulate-success", response_model=PaymentOut)
def success(payment_id: UUID, db: DB, user: CurrentUser):
    return payments.simulate(db, payment_id, user, True)


@router.post("/payments/{payment_id}/simulate-failure", response_model=PaymentOut)
def failure(payment_id: UUID, data: FailureInput, db: DB, user: CurrentUser):
    return payments.simulate(db, payment_id, user, False, data.reason)
