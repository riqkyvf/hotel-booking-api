from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    connect_args={"options": "-c timezone=UTC -c lock_timeout=10000 -c statement_timeout=30000"},
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def db_now(session):
    # Read wall-clock time AFTER acquiring business locks, not transaction start time.
    return session.scalar(select(func.clock_timestamp()))


def get_db():
    from app.core.errors import BusinessError

    with SessionLocal() as session:
        try:
            yield session
            session.commit()
        except BusinessError as exc:
            if exc.persist:
                session.commit()
            else:
                session.rollback()
            raise
        except Exception:
            session.rollback()
            raise
