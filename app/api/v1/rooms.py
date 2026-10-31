from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from app.api.dependencies import DB, Admin, OptionalUser
from app.models import Room
from app.schemas import (
    AvailabilityOut,
    AvailabilityPatch,
    Page,
    RoomInput,
    RoomOut,
    RoomType,
    StayQuery,
)
from app.services import bookings, catalog
from app.services.common import order, page, validate_range

router = APIRouter(tags=["Rooms"])


@router.get("/hotels/{hotel_id}/rooms", response_model=Page[RoomOut])
def list_rooms(
    hotel_id: UUID,
    db: DB,
    user: OptionalUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    min_price: Annotated[Decimal | None, Query(ge=0, le=9999999999.99)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0, le=9999999999.99)] = None,
    min_capacity: Annotated[int | None, Query(ge=1, le=10)] = None,
    type: RoomType | None = None,
    sort: str = "price",
    include_archived: bool = False,
):
    catalog.archive_access(include_archived, user)
    catalog.get_hotel(db, hotel_id, user)
    validate_range(min_price, max_price)
    stmt = select(Room).where(Room.hotel_id == hotel_id)
    if not include_archived:
        stmt = stmt.where(Room.is_archived.is_(False))
    if min_price is not None:
        stmt = stmt.where(Room.price_per_night >= min_price)
    if max_price is not None:
        stmt = stmt.where(Room.price_per_night <= max_price)
    if min_capacity is not None:
        stmt = stmt.where(Room.capacity >= min_capacity)
    if type is not None:
        stmt = stmt.where(Room.type == type)
    return page(
        db,
        order(
            stmt,
            sort,
            {
                "price": Room.price_per_night,
                "capacity": Room.capacity,
                "room_number": Room.room_number,
            },
            Room.id,
        ),
        limit,
        offset,
    )


@router.get("/rooms/{room_id}", response_model=RoomOut)
def get_room(room_id: UUID, db: DB, user: OptionalUser):
    return catalog.get_room(db, room_id, user)


@router.post("/hotels/{hotel_id}/rooms", response_model=RoomOut, status_code=201)
def create_room(hotel_id: UUID, data: RoomInput, db: DB, admin: Admin):
    return catalog.create_room(db, hotel_id, data)


@router.put("/rooms/{room_id}", response_model=RoomOut)
def update_room(room_id: UUID, data: RoomInput, db: DB, admin: Admin):
    return catalog.update_room(db, room_id, data=data)


@router.patch("/rooms/{room_id}/availability", response_model=RoomOut)
def patch_availability(room_id: UUID, data: AvailabilityPatch, db: DB, admin: Admin):
    return catalog.update_room(db, room_id, availability=data.is_available)


@router.delete("/rooms/{room_id}", status_code=204)
def archive_room(room_id: UUID, db: DB, admin: Admin):
    catalog.archive_room(db, room_id)
    return Response(status_code=204)


@router.get("/rooms/{room_id}/availability", response_model=AvailabilityOut)
def get_availability(room_id: UUID, stay: Annotated[StayQuery, Query()], db: DB):
    return bookings.availability(db, room_id, stay)
