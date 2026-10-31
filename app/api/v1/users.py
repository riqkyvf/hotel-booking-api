from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.dependencies import DB, Admin, CurrentUser
from app.models import User
from app.schemas import AdminUserPatch, Page, ProfilePatch, Role, UserOut
from app.services import users
from app.services.common import order, page, require

router = APIRouter(tags=["Users"])


@router.get("/users/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@router.patch("/users/me", response_model=UserOut)
def profile(data: ProfilePatch, db: DB, user: CurrentUser):
    return users.update_profile(db, user, data)


@router.get("/admin/users", response_model=Page[UserOut])
def list_users(
    db: DB,
    admin: Admin,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    role: Role | None = None,
    is_active: bool | None = None,
    sort: str = "created_at",
):
    stmt = select(User)
    if role is not None:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    return page(
        db,
        order(stmt, sort, {"created_at": User.created_at, "email": User.email}, User.id),
        limit,
        offset,
    )


@router.get("/admin/users/{user_id}", response_model=UserOut)
def get_user(user_id: UUID, db: DB, admin: Admin):
    return require(db.get(User, user_id))


@router.patch("/admin/users/{user_id}", response_model=UserOut)
def patch_user(user_id: UUID, data: AdminUserPatch, db: DB, admin: Admin):
    return users.update_admin(db, user_id, data)
