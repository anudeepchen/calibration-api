from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator


def clean(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Must not be blank")
    return value


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return value.astimezone(timezone.utc)


TextInput = Annotated[str, AfterValidator(clean)]


class CalibrationCreate(BaseModel):
    calibration_type: TextInput
    value: Decimal = Field(
        allow_inf_nan=False,
        description=(
            "Accepts finite JSON numbers or decimal strings. Use strings for exact precision; "
            "responses serialize decimals as strings."
        ),
    )
    username: TextInput
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("value", mode="before")
    @classmethod
    def exact_decimal(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Booleans are not calibration values")
        if isinstance(value, float):
            # JSON parsing has already produced a float. Avoid Decimal(float), which
            # exposes its binary expansion; strings retain the caller's exact precision.
            return Decimal(str(value))
        return value

    @field_validator("recorded_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return utc(value)


class CalibrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    calibration_type: str
    value: Decimal = Field(description="Exact numeric value serialized as a JSON string.")
    username: str
    recorded_at: Annotated[datetime, AfterValidator(utc)]


class TagInput(BaseModel):
    tag: TextInput


class MembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    calibration_id: UUID
    tag: str
    added_at: Annotated[datetime, AfterValidator(utc)]
    removed_at: Annotated[datetime, AfterValidator(utc)] | None


class CalibrationPage(BaseModel):
    items: list[CalibrationOut]
    limit: int
    offset: int


class TagsOut(BaseModel):
    tags: list[str] = Field(
        description="Distinct matching tag names in case-sensitive sorted order."
    )
