from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash("not-a-real-user-password")


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def issue_token(user_id) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=settings.jwt_minutes),
            "iss": "hotel-api",
            "aud": "hotel-api",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_token(token):
    return jwt.decode(
        token,
        get_settings().jwt_secret,
        algorithms=["HS256"],
        issuer="hotel-api",
        audience="hotel-api",
        options={"require": ["sub", "exp", "iat"]},
    )
