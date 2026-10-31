from fastapi import APIRouter

from app.api.v1 import auth, bookings, health, hotels, payments, rooms, users
from app.schemas import ErrorOut

router = APIRouter(
    prefix="/api/v1",
    responses={code: {"model": ErrorOut} for code in (401, 403, 404, 409, 422, 500, 503)},
)
for module in (auth, users, hotels, rooms, bookings, payments, health):
    router.include_router(module.router)
