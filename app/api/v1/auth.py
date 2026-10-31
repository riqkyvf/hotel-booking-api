from fastapi import APIRouter

from app.api.dependencies import DB
from app.core.config import get_settings
from app.core.security import issue_token
from app.schemas import Login, Register, TokenOut, UserOut
from app.services import users

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserOut, status_code=201, summary="Register a user")
def register(data: Register, db: DB):
    return users.register(db, data)


@router.post("/login", response_model=TokenOut, summary="Obtain a JWT (JSON credentials)")
def login(data: Login, db: DB):
    user = users.login(db, data)
    return TokenOut(access_token=issue_token(user.id), expires_in=get_settings().jwt_minutes * 60)
