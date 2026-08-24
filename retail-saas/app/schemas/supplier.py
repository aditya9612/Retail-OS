from datetime import datetime
from typing import Optional

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    field_validator,
)
from typing import Any, Optional

class SupplierBase(BaseModel):

    name: str = Field(
        min_length=2,
        max_length=255,
        description="Supplier name must be between 2 and 255 characters"
    )

    contact_person: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=255,
        description="Contact person name must be between 2 and 255 characters"
    )

    email: Optional [EmailStr] = Field(
        default=None,
        description="Enter a valid email address"
    )

    phone: Optional[str] = Field(
        default=None,
        min_length=10,
        max_length=13,
        description="Indian phone number: 10 digits or +91 followed by 10 digits"
    )

    address: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=500,
        description="Address must be between 2 and 500 characters"
    )

    gstin: Optional[str] = Field(
        default=None,
        min_length=15,
        max_length=15,
        description="GSTIN must be exactly 15 characters"
    )

    @field_validator("name", "contact_person", "address")
    @classmethod
    def validate_text_fields(cls, value: str) -> str:

        value = value.strip()

        if not value:
            raise ValueError("Field cannot be empty or whitespace")

        return value

    @field_validator("name", "contact_person")
    @classmethod
    def validate_person_name(cls, value: str) -> str:

        value = value.strip()

        if not all(
            char.isalpha() or char.isspace() or char in ".'-"
            for char in value
        ):
            raise ValueError(
                "Name can contain only letters, spaces, '.', '-' and '''"
            )

        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(
        cls,
        value: Optional[str],
    ) -> Optional[str]:

        if value is None:
           return None

        value = value.strip()

        if value.startswith("+91"):
           number = value[3:]

           if len(number) != 10:
              raise ValueError(
                "Phone number with +91 must contain exactly 10 digits after +91"
            )
        else:
           number = value

           if len(number) != 10:
              raise ValueError(
                "Phone number must contain exactly 10 digits"
            )

        if not number.isdigit():
           raise ValueError(
              "Phone number must contain digits only"
            )

        if number[0] not in "6789":
           raise ValueError(
              "Indian phone number must start with 6, 7, 8 or 9"
            )

        return value

    @field_validator("gstin")
    @classmethod
    def validate_gstin(cls, value: str) -> str:

        value = value.strip().upper()

        if len(value) != 15:
            raise ValueError(
                "GSTIN must be exactly 15 characters"
            )

        if not (
            value[:2].isdigit()
            and value[2:7].isalpha()
            and value[7:11].isdigit()
            and value[11].isalpha()
            and value[12] == "Z"
            and value[13:15].isalnum()
        ):
            raise ValueError(
                "Invalid Indian GSTIN format"
            )

        return value


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):

    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=255
    )

    contact_person: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=255
    )

    email: Optional[EmailStr] = None

    phone: Optional[str] = None

    address: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=500
    )

    gstin: Optional[str] = Field(
        default=None,
        min_length=15,
        max_length=15
    )

    @field_validator("name", "contact_person", "address")
    @classmethod
    def validate_update_text_fields(
        cls,
        value: Optional[str]
    ) -> Optional[str]:

        if value is None:
            return value

        value = value.strip()

        if not value:
            raise ValueError(
                "Field cannot be empty or whitespace"
            )

        return value

    @field_validator("name", "contact_person")
    @classmethod
    def validate_update_names(
        cls,
        value: Optional[str]
    ) -> Optional[str]:

        if value is None:
            return value

        if not all(
            char.isalpha() or char.isspace() or char in ".'-"
            for char in value
        ):
            raise ValueError(
                "Name can contain only letters, spaces, '.', '-' and '''"
            )

        return value

    @field_validator("phone")
    @classmethod
    def validate_update_phone(
        cls,
        value: Optional[str]
    ) -> Optional[str]:

        if value is None:
            return value

        value = value.strip()

        if value.startswith("+91"):
            number = value[3:]

            if len(number) != 10:
                raise ValueError(
                    "Phone number with +91 must contain exactly 10 digits after +91"
                )
        else:
            number = value

            if len(number) != 10:
                raise ValueError(
                    "Phone number must contain exactly 10 digits"
                )

        if not number.isdigit():
            raise ValueError(
                "Phone number must contain digits only"
            )

        if number[0] not in "6789":
            raise ValueError(
                "Indian phone number must start with 6, 7, 8 or 9"
            )

        return value

    @field_validator("gstin")
    @classmethod
    def validate_update_gstin(
        cls,
        value: Optional[str]
    ) -> Optional[str]:

        if value is None:
            return value

        value = value.strip().upper()

        if len(value) != 15:
            raise ValueError(
                "GSTIN must be exactly 15 characters"
            )

        if not (
            value[:2].isdigit()
            and value[2:7].isalpha()
            and value[7:11].isdigit()
            and value[11].isalpha()
            and value[12] == "Z"
            and value[13:15].isalnum()
        ):
            raise ValueError(
                "Invalid Indian GSTIN format"
            )

        return value


class SupplierResponse(BaseModel):

    id: int
    tenant_id: int
    name: str
    contact_person: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    gstin: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = {
        "from_attributes": True
    }
    
class SupplierStatsResponse(BaseModel):

    total_suppliers: int
    active_suppliers: int
    inactive_suppliers: int


class SupplierStatusUpdate(BaseModel):

    is_active: bool
    
class SupplierPurchaseHistoryResponse(BaseModel):
    supplier_id: int
    supplier_name: str
    total_purchases: int
    purchase_history: list[Any]
    message: str