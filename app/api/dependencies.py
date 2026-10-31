from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.errors import BusinessError
from app.core.security import decode_token
from app.db.session import get_db
from app.models import User

DB = Annotated[Session, Depends(get_db, scope="function")]
bearer = HTTPBearer(auto_error=False)


def current_user(
    db: DB, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> User:
    try:
        if credentials is None:
            raise ValueError()
        user_id = UUID(decode_token(credentials.credentials)["sub"])
    except (InvalidTokenError, ValueError, KeyError, TypeError):
        raise BusinessError(401, "UNAUTHORIZED", "A valid Bearer token is required.") from None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise BusinessError(401, "UNAUTHORIZED", "Account is unavailable.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def optional_user(
    db: DB, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
):
    return current_user(db, credentials) if credentials else None


OptionalUser = Annotated[User | None, Depends(optional_user)]


def admin_user(user: CurrentUser) -> User:
    if user.role != "admin":
        raise BusinessError(403, "FORBIDDEN", "Administrator role required.")
    return user


Admin = Annotated[User, Depends(admin_user)]
