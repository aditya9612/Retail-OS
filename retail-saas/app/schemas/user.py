
from datetime import datetime
from typing import Any, Optional
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.utils.validators import validate_pan_number, validate_aadhaar_number, validate_email_address
from app.utils.phone import normalize_phone_number


PHONE_PATTERN = re.compile(r"^(?:\+91)?[6-9]\d{9}$")

FULL_NAME_PATTERN = re.compile(
    r"^[A-Za-zÀ-ÖØ-öø-ÿ]+(?:[ .'-][A-Za-zÀ-ÖØ-öø-ÿ]+)*$"
)

SPECIAL_CHARACTERS = r"""!@#$%^&*()_+\-=[]{};':"\|,.<>/?`~"""


class UserBase(BaseModel):

    email: EmailStr = Field(
        description="Valid email address is required"
    )

    full_name: str = Field(
        min_length=2,
        max_length=100,
    )

    phone: Optional[str] = Field(
        default=None,
    )

    store_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional Store ID. Can be assigned later via /users/{user_id}/assign-store",
    )

    role_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Role ID from GET /api/v1/roles. Optional if 'role' name is provided.",
    )

    role: Optional[str] = Field(
        default=None,
        description="Role name (e.g. manager, staff, admin, owner). Automatically mapped to role_id.",
    )

    pancard: Optional[str] = Field(
        default=None,
        description="PAN card number or uploaded document URL",
    )

    addhar_card: Optional[str] = Field(
        default=None,
        description="Aadhaar card number or uploaded document URL",
    )

    profile_photo: Optional[str] = Field(
        default=None,
        description="Profile photo URL or file path",
    )

    pan_number: Optional[str] = Field(
        default=None,
        description="PAN card number (e.g. ABCDE1234F)",
    )

    addhar_number: Optional[str] = Field(
        default=None,
        description="Aadhaar card 12-digit number",
    )

    @field_validator("pan_number")
    @classmethod
    def validate_pan(cls, value: Optional[str]) -> Optional[str]:
        return validate_pan_number(value)

    @field_validator("addhar_number", mode="before")
    @classmethod
    def validate_aadhaar(cls, value: Any) -> Optional[str]:
        return validate_aadhaar_number(value)


    @field_validator("email")
    @classmethod
    def validate_email(cls, value: EmailStr) -> str:
        return validate_email_address(str(value), field_name="Email", required=True)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()

        if len(value) < 2:
            raise ValueError(
                "Full name must contain at least 2 characters"
            )

        if len(value) > 100:
            raise ValueError(
                "Full name cannot exceed 100 characters"
            )

        if not FULL_NAME_PATTERN.fullmatch(value):
            raise ValueError(
                "Full name may contain only letters, spaces, dots, hyphens and apostrophes"
            )

        if not any(char.isalpha() for char in value):
            raise ValueError(
                "Full name must contain alphabetic characters"
            )

        return value

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return normalize_phone_number(value)


class UserCreate(UserBase):

    phone: str = Field(
        ...,
        description="Mandatory 10-digit Indian phone number",
    )

    role: str = Field(
        "staff",
        description="Role name (e.g. staff, manager, cashier, admin, accountant)",
    )

    password: str = Field(
        min_length=8,
        max_length=100,
    )

    @field_validator("phone", mode="before")
    @classmethod
    def validate_create_phone(cls, value: Any) -> str:
        if value is None or not str(value).strip():
            raise ValueError("Phone number is required")
        return normalize_phone_number(str(value).strip())

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:

        if not value.strip():
            raise ValueError("Password cannot be empty")

        if len(value) < 8:
            raise ValueError(
                "Password must be at least 8 characters"
            )

        if len(value) > 100:
            raise ValueError(
                "Password cannot exceed 100 characters"
            )

        if not any(char.isupper() for char in value):
            raise ValueError(
                "Password must contain at least one uppercase letter"
            )

        if not any(char.islower() for char in value):
            raise ValueError(
                "Password must contain at least one lowercase letter"
            )

        if not any(char.isdigit() for char in value):
            raise ValueError(
                "Password must contain at least one number"
            )

        if not any(char in SPECIAL_CHARACTERS for char in value):
            raise ValueError(
                "Password must contain at least one special character"
            )

        return value

    @model_validator(mode="after")
    def validate_role_specified(self):
        if not self.role_id and not (self.role and self.role.strip()):
            raise ValueError("Either 'role' (e.g. 'manager', 'staff') or 'role_id' must be provided")
        return self


class UserUpdate(BaseModel):

    full_name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    phone: Optional[str] = Field(
        default=None,
    )

    store_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    role_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Role ID from GET /api/v1/roles.",
    )

    is_active: Optional[bool] = None

    password: Optional[str] = Field(
        default=None,
        min_length=8,
        max_length=100,
    )

    pancard: Optional[str] = Field(
        default=None,
    )

    addhar_card: Optional[str] = Field(
        default=None,
    )

    profile_photo: Optional[str] = Field(
        default=None,
    )

    pan_number: Optional[str] = Field(
        default=None,
    )

    addhar_number: Optional[str] = Field(
        default=None,
    )

    @field_validator("pan_number")
    @classmethod
    def validate_pan(cls, value: Optional[str]) -> Optional[str]:
        return validate_pan_number(value)

    @field_validator("addhar_number", mode="before")
    @classmethod
    def validate_aadhaar(cls, value: Any) -> Optional[str]:
        return validate_aadhaar_number(value)

    model_config = ConfigDict(
        extra="forbid",
    )

    @field_validator("full_name")
    @classmethod
    def validate_full_name(
        cls,
        value: Optional[str],
    ) -> Optional[str]:

        if value is None:
            return value

        value = value.strip()

        if len(value) < 2:
            raise ValueError(
                "Full name must contain at least 2 characters"
            )

        if len(value) > 100:
            raise ValueError(
                "Full name cannot exceed 100 characters"
            )

        if not FULL_NAME_PATTERN.fullmatch(value):
            raise ValueError(
                "Full name may contain only letters, spaces, dots, hyphens and apostrophes"
            )

        return value

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return normalize_phone_number(value)

    @field_validator("password")
    @classmethod
    def validate_password(
        cls,
        value: Optional[str],
    ) -> Optional[str]:

        if value is None:
            return value

        if not value.strip():
            raise ValueError("Password cannot be empty")

        if len(value) < 8:
            raise ValueError(
                "Password must be at least 8 characters"
            )

        if len(value) > 100:
            raise ValueError(
                "Password cannot exceed 100 characters"
            )

        if not any(char.isupper() for char in value):
            raise ValueError(
                "Password must contain at least one uppercase letter"
            )

        if not any(char.islower() for char in value):
            raise ValueError(
                "Password must contain at least one lowercase letter"
            )

        if not any(char.isdigit() for char in value):
            raise ValueError(
                "Password must contain at least one number"
            )

        if not any(char in SPECIAL_CHARACTERS for char in value):
            raise ValueError(
                "Password must contain at least one special character"
            )

        return value

    @model_validator(mode="after")
    def validate_updates(self):

        if not self.model_fields_set:
            raise ValueError(
                "At least one field must be provided for update"
            )

        if (
            "full_name" in self.model_fields_set
            and self.full_name is None
        ):
            raise ValueError("Full name cannot be null")

        if (
            "phone" in self.model_fields_set
            and self.phone is None
        ):
            raise ValueError("Phone cannot be null")

        if (
            "password" in self.model_fields_set
            and self.password is None
        ):
            raise ValueError("Password cannot be null")

        return self


class MyProfileUpdate(BaseModel):

    full_name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    phone: Optional[str] = Field(
        default=None,
    )

    model_config = ConfigDict(
        extra="forbid",
    )

    @field_validator("full_name")
    @classmethod
    def validate_full_name(
        cls,
        value: Optional[str],
    ) -> Optional[str]:

        if value is None:
            return value

        value = value.strip()

        if len(value) < 2:
            raise ValueError(
                "Full name must contain at least 2 characters"
            )

        if len(value) > 100:
            raise ValueError(
                "Full name cannot exceed 100 characters"
            )

        if not FULL_NAME_PATTERN.fullmatch(value):
            raise ValueError(
                "Full name may contain only letters, spaces, dots, hyphens and apostrophes"
            )

        return value

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return normalize_phone_number(value)

    @model_validator(mode="after")
    def validate_updates(self):

        if not self.model_fields_set:
            raise ValueError(
                "At least one field must be provided for update"
            )

        if (
            "full_name" in self.model_fields_set
            and self.full_name is None
        ):
            raise ValueError("Full name cannot be null")

        if (
            "phone" in self.model_fields_set
            and self.phone is None
        ):
            raise ValueError("Phone cannot be null")

        return self


class RoleResponse(BaseModel):

    id: int
    name: str
    permissions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(
        from_attributes=True,
    )


class UserResponse(BaseModel):

    id: int
    tenant_id: int
    email: str
    full_name: str
    phone: Optional[str]
    store_id: Optional[int]
    role_id: int
    is_active: bool
    role: Optional[RoleResponse] = None
    created_at: datetime
    pancard: Optional[str] = None
    addhar_card: Optional[str] = None
    profile_photo: Optional[str] = None
    pan_number: Optional[str] = None
    addhar_number: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
    )


class AssignStoreRequest(BaseModel):
    store_id: int = Field(
        ...,
        gt=0,
        description="Store ID to assign to the user",
    )


class AssignStoreResponse(BaseModel):
    message: str = "Store assigned successfully"
    user_id: int
    store_id: int
    store_name: Optional[str] = None
    role: Optional[str] = None


class RemoveStoreRequest(BaseModel):
    store_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional Store ID to verify before removing user from store. If provided, ensures user is assigned to this store.",
    )


class RemoveStoreResponse(BaseModel):
    message: str = "User removed from store successfully"
    user_id: int
    store_id: Optional[int] = None
    previous_store_id: Optional[int] = None
    role: Optional[str] = None


class StoreUserItem(BaseModel):
    id: int
    full_name: str
    email: str
    phone: Optional[str] = None
    role_id: int
    role_name: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


class StoreUsersSummary(BaseModel):
    store_id: Optional[int] = Field(
        default=None,
        description="Store ID, or null for unassigned / head office users",
    )
    store_name: str
    store_code: Optional[str] = None
    is_main: bool = False
    total_users: int
    users: list[StoreUserItem] = Field(default_factory=list)

    model_config = ConfigDict(
        from_attributes=True,
    )


class UsersByStoreResponse(BaseModel):
    total_stores: int
    total_users: int
    stores: list[StoreUsersSummary]

    model_config = ConfigDict(
        from_attributes=True,
    )

