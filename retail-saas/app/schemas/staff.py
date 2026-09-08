import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class StaffCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=100
    )

    email: str

    phone: str

    role: str

    is_active: bool = True

    @field_validator("phone")
    @classmethod
    def validate_indian_mobile(cls, value: str) -> str:
        value = value.strip()

        if not re.fullmatch(r"[6-9][0-9]{9}", value):
            raise ValueError(
                "Enter a valid Indian mobile number with exactly 10 digits "
                "starting with 6, 7, 8, or 9"
            )

        return value

    @field_validator("email")
    @classmethod
    def validate_gmail(cls, value: str) -> str:
        value = value.strip().lower()

        if not re.fullmatch(
            r"[a-zA-Z0-9._%+-]+@gmail\.com",
            value
        ):
            raise ValueError("Enter a valid Gmail address")

        return value


class StaffResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    role: str
    store_id: int
    is_active: bool

    model_config = {
        "from_attributes": True
    }


class StaffUpdate(BaseModel):
    name: Optional[str] = Field(
        None,
        min_length=2,
        max_length=100
    )

    email: Optional[str] = None

    phone: Optional[str] = None

    role: Optional[str] = None

    store_id: Optional[int] = Field(
        None,
        gt=0
    )

    is_active: Optional[bool] = None

    @field_validator("phone")
    @classmethod
    def validate_indian_mobile(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        value = value.strip()

        if not re.fullmatch(r"[6-9][0-9]{9}", value):
            raise ValueError(
                "Enter a valid Indian mobile number with exactly 10 digits "
                "starting with 6, 7, 8, or 9"
            )

        return value

    @field_validator("email")
    @classmethod
    def validate_gmail(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        value = value.strip().lower()

        if not re.fullmatch(
            r"[a-zA-Z0-9._%+-]+@gmail\.com",
            value
        ):
            raise ValueError("Enter a valid Gmail address")

        return value


class StaffAssign(BaseModel):
    staff_id: int = Field(
        ...,
        gt=0
    )

    store_id: int = Field(
        ...,
        gt=0
    )


class StaffTransfer(BaseModel):
    staff_id: int = Field(
        ...,
        gt=0
    )

    source_store_id: int = Field(
        ...,
        gt=0
    )

    destination_store_id: int = Field(
        ...,
        gt=0
    )