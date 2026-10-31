import logging
from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException

log = logging.getLogger(__name__)


class BusinessError(Exception):
    def __init__(self, status: int, code: str, message: str, *, persist=False, details=None):
        self.status, self.code, self.message = status, code, message
        self.persist, self.details = persist, details or []


def error_response(request, status, code, message, details=None, headers=None):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or [],
                "request_id": getattr(request.state, "request_id", str(uuid4())),
            }
        },
        headers=headers,
    )


def install_handlers(app):
    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(BusinessError)
    async def business(request, exc):
        return error_response(
            request,
            exc.status,
            exc.code,
            exc.message,
            exc.details,
            {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation(request, exc):
        # Do not echo request bodies, passwords, tokens or raw validator inputs.
        details = [
            {"field": ".".join(map(str, e["loc"])), "message": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        return error_response(request, 422, "VALIDATION_ERROR", "Invalid request data.", details)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "UNAUTHORIZED", 403: "FORBIDDEN"}
        return error_response(
            request,
            exc.status_code,
            codes.get(exc.status_code, "HTTP_ERROR"),
            str(exc.detail),
            headers=exc.headers,
        )

    @app.exception_handler(IntegrityError)
    async def integrity(request, exc):
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
        codes = {
            "uq_users_email": "EMAIL_EXISTS",
            "uq_room_number": "ROOM_NUMBER_EXISTS",
            "no_overlapping_bookings": "ROOM_NOT_AVAILABLE",
        }
        return error_response(
            request,
            409,
            codes.get(constraint, "RESOURCE_CONFLICT"),
            "Operation conflicts with existing data.",
        )

    @app.exception_handler(OperationalError)
    async def database_error(request, exc):
        if getattr(exc.orig, "sqlstate", "") in {"55P03", "40P01", "40001", "57014"}:
            return error_response(request, 409, "CONCURRENT_OPERATION", "Retry the operation.")
        log.exception("Database unavailable: request %s", request.state.request_id)
        return error_response(
            request, 503, "DATABASE_UNAVAILABLE", "Database temporarily unavailable."
        )

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        log.exception("Unhandled error: request %s", request.state.request_id)
        response = error_response(request, 500, "INTERNAL_ERROR", "Internal server error.")
        response.headers["X-Request-ID"] = request.state.request_id
        return response
