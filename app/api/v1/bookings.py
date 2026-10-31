from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.dependencies import DB, CurrentUser
from app.core.errors import BusinessError
from app.models import Booking, Room
from app.schemas import BookingInput, BookingOut, BookingStatus, Page
from app.services import bookings
from app.services.common import order, page, validate_range

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.post(
    "",
    response_model=BookingOut,
    status_code=201,
    description="Idempotency-Key is required. Replays return the original creation snapshot, including after cancellation or expiry.",
)
def create_booking(
    data: BookingInput,
    db: DB,
    user: CurrentUser,
    key: Annotated[
        str,
        Header(
            alias="Idempotency-Key", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"
        ),
    ],
):
    body, replayed = bookings.create_booking(db, user, data, key)
    return JSONResponse(
        status_code=201,
        content=body,
        headers={
            "Idempotency-Replayed": str(replayed).lower(),
            "Location": f"/api/v1/bookings/{body['id']}",
        },
    )


@router.get("", response_model=Page[BookingOut])
def list_bookings(
    db: DB,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: BookingStatus | None = None,
    hotel_id: UUID | None = None,
    user_id: UUID | None = None,
    check_in_from: date | None = None,
    check_in_to: date | None = None,
    sort: str = "-created_at",
):
    validate_range(check_in_from, check_in_to)
    if user_id is not None and user.role != "admin":
        raise BusinessError(403, "FORBIDDEN", "Only administrators may filter by user_id.")
    stmt = select(Booking).join(Room, Booking.room_id == Room.id)
    if user.role != "admin":
        stmt = stmt.where(Booking.user_id == user.id)
    elif user_id is not None:
        stmt = stmt.where(Booking.user_id == user_id)
    if hotel_id is not None:
        stmt = stmt.where(Room.hotel_id == hotel_id)
    if check_in_from is not None:
        stmt = stmt.where(Booking.check_in >= check_in_from)
    if check_in_to is not None:
        stmt = stmt.where(Booking.check_in <= check_in_to)
    # Reconcile BEFORE filtering by state, to make the deadline visible to reads.
    room_ids = list(db.scalars(stmt.with_only_columns(Booking.room_id).distinct()))
    bookings.settle_selection(db, room_ids)
    if status is not None:
        stmt = stmt.where(Booking.status == status)
    return page(
        db,
        order(
            stmt,
            sort,
            {
                "created_at": Booking.created_at,
                "check_in": Booking.check_in,
                "total_price": Booking.total_price,
            },
            Booking.id,
        ),
        limit,
        offset,
    )


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: UUID, db: DB, user: CurrentUser):
    booking, _ = bookings.locked_booking(db, booking_id, user)
    return booking


@router.patch("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: UUID, db: DB, user: CurrentUser):
    return bookings.cancel_booking(db, booking_id, user)
