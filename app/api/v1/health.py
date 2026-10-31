from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DB
from app.core.errors import BusinessError
from app.schemas import HealthOut

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", response_model=HealthOut)
def live():
    return {"status": "alive"}


@router.get("/ready", response_model=HealthOut)
def ready(db: DB):
    try:
        db.execute(text("SELECT 1"))
        current = db.scalar(text("SELECT version_num FROM alembic_version"))
    except SQLAlchemyError:
        raise BusinessError(
            503, "DATABASE_NOT_READY", "Database or migration metadata is unavailable."
        ) from None
    if current != "0001_initial":
        raise BusinessError(503, "SCHEMA_NOT_READY", "Database schema revision is not current.")
    return {"status": "ready"}
