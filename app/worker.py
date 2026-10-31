import logging
import signal
import threading
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal, db_now
from app.models import Booking
from app.services.bookings import lock_room, settle_room

log = logging.getLogger(__name__)
stop = threading.Event()


def run_once():
    with SessionLocal() as db:
        ids = list(
            db.scalars(
                select(Booking.room_id)
                .where(Booking.status.in_(("pending_payment", "confirmed")))
                .distinct()
            )
        )
    for room_id in ids:
        # Each room is a separate transaction; other rooms remain usable.
        with SessionLocal.begin() as db:
            lock_room(db, room_id)
            settle_room(db, room_id, db_now(db))


def main():
    logging.basicConfig(level=logging.INFO)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        try:
            run_once()
            Path("/tmp/hotel-worker-heartbeat").touch()
        except Exception:
            log.exception("Lifecycle reconciliation failed; will retry")
        stop.wait(get_settings().worker_interval_seconds)


if __name__ == "__main__":
    main()
