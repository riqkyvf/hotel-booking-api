from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response
from sqlalchemy import func, select

from app.api.dependencies import DB, Admin, OptionalUser
from app.models import Hotel, Room
from app.schemas import HotelInput, HotelOut, Page
from app.services import catalog
from app.services.common import order, page, validate_range

router = APIRouter(prefix="/hotels", tags=["Hotels"])


@router.get("", response_model=Page[HotelOut])
def list_hotels(
    db: DB,
    user: OptionalUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    city: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    min_rating: Annotated[Decimal | None, Query(ge=0, le=5)] = None,
    max_rating: Annotated[Decimal | None, Query(ge=0, le=5)] = None,
    min_price: Annotated[Decimal | None, Query(ge=0, le=9999999999.99)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0, le=9999999999.99)] = None,
    sort: str = "name",
    include_archived: bool = False,
):
    catalog.archive_access(include_archived, user)
    validate_range(min_rating, max_rating)
    validate_range(min_price, max_price)
    stmt = select(Hotel)
    if not include_archived:
        stmt = stmt.where(Hotel.is_archived.is_(False))
    if city is not None:
        stmt = stmt.where(func.lower(Hotel.city) == city.strip().lower())
    if min_rating is not None:
        stmt = stmt.where(Hotel.rating >= min_rating)
    if max_rating is not None:
        stmt = stmt.where(Hotel.rating <= max_rating)
    active_room = (
        Room.hotel_id == Hotel.id,
        Room.is_archived.is_(False),
        Room.is_available.is_(True),
    )
    if min_price is not None or max_price is not None:
        sub = select(Room.id).where(*active_room)
        if min_price is not None:
            sub = sub.where(Room.price_per_night >= min_price)
        if max_price is not None:
            sub = sub.where(Room.price_per_night <= max_price)
        stmt = stmt.where(sub.exists())
    minimum_price = (
        select(func.min(Room.price_per_night))
        .where(*active_room)
        .correlate(Hotel)
        .scalar_subquery()
    )
    return page(
        db,
        order(
            stmt,
            sort,
            {"name": Hotel.name, "rating": Hotel.rating, "price": minimum_price},
            Hotel.id,
        ),
        limit,
        offset,
    )


@router.get("/{hotel_id}", response_model=HotelOut)
def get_hotel(hotel_id: UUID, db: DB, user: OptionalUser):
    return catalog.get_hotel(db, hotel_id, user)


@router.post("", response_model=HotelOut, status_code=201)
def create_hotel(data: HotelInput, db: DB, admin: Admin):
    return catalog.create_hotel(db, data)


@router.put("/{hotel_id}", response_model=HotelOut)
def update_hotel(hotel_id: UUID, data: HotelInput, db: DB, admin: Admin):
    return catalog.update_hotel(db, hotel_id, data)


@router.delete("/{hotel_id}", status_code=204)
def archive_hotel(hotel_id: UUID, db: DB, admin: Admin):
    catalog.archive_hotel(db, hotel_id)
    return Response(status_code=204)
