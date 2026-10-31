import re
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Generic, TypeVar
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Money = Annotated[Decimal, Field(gt=0, le=9999999999.99, max_digits=12, decimal_places=2)]


class Role(StrEnum):
    user = "user"
    admin = "admin"


class RoomType(StrEnum):
    single = "single"
    double = "double"
    twin = "twin"
    family = "family"
    suite = "suite"


class BookingStatus(StrEnum):
    pending_payment = "pending_payment"
    confirmed = "confirmed"
    cancelled = "cancelled"
    expired = "expired"
    completed = "completed"


class PaymentStatus(StrEnum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    refunded = "refunded"


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EmailInput(Input):
    email: Annotated[EmailStr, Field(max_length=254)]

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class Login(EmailInput):
    password: Annotated[
        str, StringConstraints(min_length=10, max_length=128, strip_whitespace=False)
    ]


class Register(Login):
    name: Name
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9]{7,15}$")


class ProfilePatch(Input):
    email: Annotated[EmailStr, Field(max_length=254)] | None = None
    name: Name | None = None
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9]{7,15}$")

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set or any(
            getattr(self, f) is None for f in self.model_fields_set - {"phone"}
        ):
            raise ValueError("Provide at least one field; only phone may be null.")
        return self


class UserOut(Output):
    id: UUID
    email: str
    name: str
    phone: str | None
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AdminUserPatch(Input):
    role: Role | None = None
    is_active: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set or any(
            getattr(self, f) is None for f in self.model_fields_set
        ):
            raise ValueError("Provide role and/or is_active; null is not allowed.")
        return self


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class HotelInput(Input):
    name: Annotated[str, StringConstraints(min_length=1, max_length=150)]
    city: Name
    address: Annotated[str, StringConstraints(min_length=1, max_length=250)]
    description: str = Field(max_length=5000)
    rating: Decimal = Field(ge=0, le=5, max_digits=2, decimal_places=1)


class HotelOut(Output):
    id: UUID
    name: str
    city: str
    address: str
    description: str
    rating: Decimal
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class RoomInput(Input):
    room_number: Annotated[str, StringConstraints(min_length=1, max_length=20)]
    type: RoomType
    capacity: int = Field(ge=1, le=10, strict=True)
    price_per_night: Money


class RoomOut(Output):
    id: UUID
    hotel_id: UUID
    room_number: str
    type: RoomType
    capacity: int
    price_per_night: Decimal
    is_available: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class AvailabilityPatch(Input):
    is_available: bool = Field(strict=True)


class Stay(Input):
    check_in: date
    check_out: date
    guests: int = Field(ge=1, le=10, strict=True)

    @field_validator("check_in", "check_out", mode="before")
    @classmethod
    def date_only(cls, value):
        if isinstance(value, str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Use YYYY-MM-DD.")
        if isinstance(value, (int, float, datetime)):
            raise ValueError("Use a calendar date.")
        return value

    @model_validator(mode="after")
    def duration(self):
        if not 1 <= (self.check_out - self.check_in).days <= 14:
            raise ValueError("Stay must be between 1 and 14 nights.")
        return self


class BookingInput(Stay):
    room_id: UUID


class StayQuery(Stay):
    # Query parameters arrive as strings, unlike JSON request-body integers.
    guests: int = Field(ge=1, le=10)


class BookingOut(Output):
    id: UUID
    user_id: UUID
    room_id: UUID
    check_in: date
    check_out: date
    guests: int
    status: BookingStatus
    price_per_night: Decimal
    total_price: Decimal
    currency: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class PaymentOut(Output):
    id: UUID
    booking_id: UUID
    amount: Decimal
    currency: str
    status: PaymentStatus
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class AvailabilityOut(BaseModel):
    room_id: UUID
    check_in: date
    check_out: date
    guests: int
    available: bool
    reason: str | None
    nights: int
    total_price: Decimal
    currency: str = "RUB"


class FailureInput(Input):
    reason: Annotated[str, StringConstraints(min_length=1, max_length=250)] = "Simulated decline"


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[dict]
    request_id: str


class ErrorOut(BaseModel):
    error: ErrorDetail


class HealthOut(BaseModel):
    status: str
