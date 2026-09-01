from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class StaffCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=100
    )

    email: EmailStr

    phone: str = Field(
        ...,
        min_length=10,
        max_length=10,
        pattern=r"^[6-9][0-9]{9}$"
    )

    role_id: int = Field(
        ...,
        gt=0
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "string",
                "email": "user@example.com",
                "phone": "string",
                "role_id": 1
            }
        }
    }


class StaffResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    store_id: int

    model_config = {
        "from_attributes": True
    }


class StaffUpdate(BaseModel):
    name: Optional[str] = Field(
        None,
        min_length=2,
        max_length=100
    )

    email: Optional[EmailStr] = None

    phone: Optional[str] = Field(
        None,
        min_length=10,
        max_length=10,
        pattern=r"^[6-9][0-9]{9}$"
    )

    role_id: Optional[int] = Field(
        None,
        gt=0
    )

    store_id: Optional[int] = Field(
        None,
        gt=0
    )

    is_active: Optional[bool] = None


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