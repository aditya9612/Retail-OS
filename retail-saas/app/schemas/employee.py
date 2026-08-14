from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class EmployeeCreate(BaseModel):
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

    store_id: int = Field(
        ...,
        gt=0
    )


class EmployeeResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    store_id: int

    class Config:
        from_attributes = True


class EmployeeUpdate(BaseModel):
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

    class Config:
        from_attributes = True