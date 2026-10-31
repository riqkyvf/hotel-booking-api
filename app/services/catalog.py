from sqlalchemy import select

from app.core.errors import BusinessError
from app.db.session import db_now
from app.models import Booking, Hotel, Room
from app.services.bookings import BLOCKING, lock_room, settle_room
from app.services.common import require


def archive_access(include_archived, user):
    if include_archived and (user is None or user.role != "admin"):
        raise BusinessError(403, "FORBIDDEN", "Administrator role required for archived resources.")


def get_hotel(db, hotel_id, user=None):
    hotel = require(db.get(Hotel, hotel_id))
    if hotel.is_archived and (user is None or user.role != "admin"):
        raise BusinessError(404, "NOT_FOUND", "Hotel not found.")
    return hotel


def get_room(db, room_id, user=None):
    room = require(db.get(Room, room_id))
    get_hotel(db, room.hotel_id, user)
    if room.is_archived and (user is None or user.role != "admin"):
        raise BusinessError(404, "NOT_FOUND", "Room not found.")
    return room


def create_hotel(db, data):
    hotel = Hotel(**data.model_dump(), is_archived=False)
    db.add(hotel)
    db.flush()
    return hotel


def update_hotel(db, hotel_id, data):
    hotel = require(db.scalar(select(Hotel).where(Hotel.id == hotel_id).with_for_update()))
    if hotel.is_archived:
        raise BusinessError(409, "RESOURCE_ARCHIVED", "Archived hotel cannot be changed.")
    for key, value in data.model_dump().items():
        setattr(hotel, key, value)
    db.flush()
    return hotel


def create_room(db, hotel_id, data):
    hotel = require(db.scalar(select(Hotel).where(Hotel.id == hotel_id).with_for_update(read=True)))
    if hotel.is_archived:
        raise BusinessError(409, "RESOURCE_ARCHIVED", "Archived hotel cannot accept rooms.")
    room = Room(hotel_id=hotel_id, **data.model_dump(), is_available=True, is_archived=False)
    db.add(room)
    db.flush()
    return room


def update_room(db, room_id, data=None, availability=None):
    hotel, room = lock_room(db, room_id)
    if room.is_archived or hotel.is_archived:
        raise BusinessError(409, "RESOURCE_ARCHIVED", "Archived room cannot be changed.")
    settle_room(db, room.id, db_now(db))
    if data:
        if db.scalar(
            select(Booking.id)
            .where(
                Booking.room_id == room.id,
                Booking.status.in_(BLOCKING),
                Booking.guests > data.capacity,
            )
            .limit(1)
        ):
            raise BusinessError(
                409, "CAPACITY_IN_USE", "Existing bookings require a larger capacity.", persist=True
            )
        for key, value in data.model_dump().items():
            setattr(room, key, value)
    if availability is not None:
        room.is_available = availability
    db.flush()
    return room


def archive_room(db, room_id):
    _, room = lock_room(db, room_id)
    settle_room(db, room.id, db_now(db))
    if db.scalar(
        select(Booking.id).where(Booking.room_id == room.id, Booking.status.in_(BLOCKING)).limit(1)
    ):
        raise BusinessError(409, "ACTIVE_BOOKINGS_EXIST", "Room has active bookings.", persist=True)
    room.is_archived, room.is_available = True, False
    db.flush()


def archive_hotel(db, hotel_id):
    hotel = require(db.scalar(select(Hotel).where(Hotel.id == hotel_id).with_for_update()))
    rooms = list(
        db.scalars(
            select(Room).where(Room.hotel_id == hotel.id).order_by(Room.id).with_for_update()
        )
    )
    for room in rooms:
        settle_room(db, room.id, db_now(db))
    if rooms and db.scalar(
        select(Booking.id)
        .where(Booking.room_id.in_([r.id for r in rooms]), Booking.status.in_(BLOCKING))
        .limit(1)
    ):
        raise BusinessError(
            409, "ACTIVE_BOOKINGS_EXIST", "Hotel has active bookings.", persist=True
        )
    hotel.is_archived = True
    for room in rooms:
        room.is_archived, room.is_available = True, False
    db.flush()
