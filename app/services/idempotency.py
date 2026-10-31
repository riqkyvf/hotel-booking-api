import hashlib
import json

from sqlalchemy import select, text

from app.core.errors import BusinessError
from app.models import IdempotencyRecord


def lock_and_lookup(db, user_id, key, payload):
    request_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    # Transaction-scoped advisory lock serializes absent records as well as existing ones.
    digest = hashlib.sha256(f"{user_id}:create_booking:{key}".encode()).digest()
    lock_id = int.from_bytes(digest[:8], signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
    record = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.operation == "create_booking",
            IdempotencyRecord.key == key,
        )
    )
    if record and record.request_hash != request_hash:
        raise BusinessError(
            409, "IDEMPOTENCY_KEY_REUSED", "Key was used with different request data."
        )
    return record, request_hash


def save(db, user_id, key, request_hash, body):
    db.add(
        IdempotencyRecord(
            user_id=user_id,
            operation="create_booking",
            key=key,
            request_hash=request_hash,
            response_status=201,
            response_body=body,
        )
    )
