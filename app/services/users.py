from sqlalchemy import func, select, text

from app.core.errors import BusinessError
from app.core.security import DUMMY_HASH, hash_password, verify_password
from app.models import User
from app.services.common import require


def register(db, data):
    if db.scalar(select(User.id).where(User.email == str(data.email))):
        raise BusinessError(409, "EMAIL_EXISTS", "Email is already registered.")
    user = User(
        email=str(data.email),
        password_hash=hash_password(data.password),
        name=data.name,
        phone=data.phone,
        role="user",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def login(db, data):
    user = db.scalar(select(User).where(User.email == str(data.email)))
    valid = verify_password(data.password, user.password_hash if user else DUMMY_HASH)
    if not valid or not user or not user.is_active:
        raise BusinessError(401, "INVALID_CREDENTIALS", "Invalid credentials or inactive account.")
    return user


def update_profile(db, user, data):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.flush()
    return user


def update_admin(db, user_id, data):
    db.execute(text("SELECT pg_advisory_xact_lock(8173409201)"))
    user = require(
        db.scalar(
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    changes = data.model_dump(exclude_unset=True)
    loses_admin = changes.get("role", user.role) != "admin" or not changes.get(
        "is_active", user.is_active
    )
    if user.role == "admin" and user.is_active and loses_admin:
        count = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "admin", User.is_active.is_(True))
        )
        if count <= 1:
            raise BusinessError(
                409, "LAST_ACTIVE_ADMIN", "At least one active administrator must remain."
            )
    for field, value in changes.items():
        setattr(user, field, value)
    db.flush()
    return user
