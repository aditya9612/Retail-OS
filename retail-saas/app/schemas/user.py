
from datetime import datetime
from typing import Any, Optional
import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

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
from app.utils.constants import RoleEnum, OFFICIAL_ROLES


PHONE_PATTERN = re.compile(r"^(?:\+91)?[6-9]\d{9}$")
PROFILE_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

FULL_NAME_PATTERN = re.compile(
    r"^[A-Za-zÀ-ÖØ-öø-ÿ]+(?:[ .'-][A-Za-zÀ-ÖØ-öø-ÿ]+)*$"
)

SPECIAL_CHARACTERS = r"""!@#$%^&*()_+\-=[]{};':"\|,.<>/?`~"""


def validate_profile_photo(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    value = value.strip()
    parsed = urlsplit(value)
    path = parsed.path
    photo_path = PurePosixPath(path)

    if parsed.scheme:
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
        ):
            raise ValueError("Profile photo must be an image URL or /uploads/users/ path")
    elif parsed.netloc or not path.startswith("/uploads/users/"):
        raise ValueError("Profile photo must be an image URL or /uploads/users/ path")

    if (
        any(part in {".", ".."} for part in photo_path.parts)
        or photo_path.suffix.lower() not in PROFILE_PHOTO_EXTENSIONS
    ):
        raise ValueError("Profile photo must be a JPG, JPEG, PNG, or WEBP image")

    return value


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
        description=f"Role name ({', '.join(OFFICIAL_ROLES)}). Automatically mapped to role_id.",
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

    @field_validator("profile_photo")
    @classmethod
    def validate_profile_photo_value(cls, value: Optional[str]) -> Optional[str]:
        return validate_profile_photo(value)

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
        examples=["9876543210"],
    )

    role: Optional[str] = Field(
        "staff",
        description="Role name (e.g. staff, manager, cashier, admin, accountant)",
        examples=["cashier"],
    )

    password: str = Field(
        min_length=8,
        max_length=100,
        examples=["SecurePass@123"],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "cashier@retailmart.com",
                "full_name": "Amit Sharma",
                "password": "SecurePassword@123",
                "phone": "9876543210",
                "role": "cashier",
                "store_id": 1,
                "pan_number": "ABCDE1234F",
                "addhar_number": "987654321012",
            }
        }
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

    @field_validator("role")
    @classmethod
    def validate_role_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip():
            clean_role = v.strip().lower()
            if len(clean_role) < 2 or len(clean_role) > 50:
                raise ValueError("Role name must be between 2 and 50 characters")
            if not clean_role[0].isalpha():
                raise ValueError("Role must start with a letter")
            if not all(c.isalnum() or c in ("_", "-", " ") for c in clean_role):
                raise ValueError(
                    f"Invalid role '{v}'. Role can only contain letters, numbers, spaces, hyphens, and underscores."
                )
            return clean_role
        return v

    @model_validator(mode="after")
    def validate_role_specified(self):
        if not self.role_id and not (self.role and self.role.strip()):
            raise ValueError("Either 'role' name or 'role_id' must be provided")
        return self


class UserUpdate(BaseModel):

    full_name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=100,
        description="Updated full name of user",
        examples=["Amit Sharma"],
    )

    phone: Optional[str] = Field(
        default=None,
        description="Updated 10-digit phone number",
        examples=["9876543210"],
    )

    store_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Assigned Store ID",
        examples=[1],
    )

    role_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Role ID from GET /api/v1/roles.",
        examples=[2],
    )

    is_active: Optional[bool] = Field(
        default=None,
        description="Account active status",
        examples=[True],
    )

    password: Optional[str] = Field(
        default=None,
        min_length=8,
        max_length=100,
        description="New account password",
        examples=["NewPassword@123!"],
    )

    pancard: Optional[str] = Field(
        default=None,
        description="PAN card document URL",
        examples=["/uploads/users/pancard_abc.pdf"],
    )

    addhar_card: Optional[str] = Field(
        default=None,
        description="Aadhaar card document URL",
        examples=["/uploads/users/addhar_xyz.pdf"],
    )

    profile_photo: Optional[str] = Field(
        default=None,
        description="Profile photo image URL",
        examples=["/uploads/users/photo_123.jpg"],
    )

    @field_validator("profile_photo")
    @classmethod
    def validate_profile_photo_value(cls, value: Optional[str]) -> Optional[str]:
        return validate_profile_photo(value)

    pan_number: Optional[str] = Field(
        default=None,
        description="PAN card number (e.g. ABCDE1234F)",
        examples=["ABCDE1234F"],
    )

    addhar_number: Optional[str] = Field(
        default=None,
        description="Aadhaar card 12-digit number",
        examples=["987654321012"],
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
        description="Updated full name",
        examples=["Amit Sharma"],
    )

    phone: Optional[str] = Field(
        default=None,
        description="Updated 10-digit phone number",
        examples=["9876543210"],
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
    id: int = Field(..., description="Role ID", examples=[1])
    name: str = Field(..., description="Role name", examples=["cashier"])
    permissions: list[str] = Field(default_factory=list, description="Assigned permission codes", examples=[["products:read", "billing:write"]])

    model_config = ConfigDict(
        from_attributes=True,
    )


class UserResponse(BaseModel):
    id: int = Field(..., description="Unique User ID", examples=[1])
    tenant_id: int = Field(..., description="Tenant ID", examples=[1])
    email: str = Field(..., description="User email address", examples=["cashier@retailmart.com"])
    full_name: str = Field(..., description="Full name of user", examples=["Amit Sharma"])
    phone: Optional[str] = Field(None, description="Normalized phone number", examples=["9876543210"])
    store_id: Optional[int] = Field(None, description="Assigned store ID", examples=[1])
    role_id: int = Field(..., description="Assigned role ID", examples=[2])
    is_active: bool = Field(True, description="Account active status", examples=[True])
    role: Optional[RoleResponse] = None
    created_at: datetime = Field(..., description="Account creation timestamp", examples=["2026-10-14T10:00:00Z"])
    pancard: Optional[str] = Field(None, description="PAN card file URL", examples=["/uploads/users/pancard_abc.pdf"])
    addhar_card: Optional[str] = Field(None, description="Aadhaar card file URL", examples=["/uploads/users/addhar_xyz.pdf"])
    profile_photo: Optional[str] = Field(None, description="Profile photo URL", examples=["/uploads/users/photo_123.jpg"])
    pan_number: Optional[str] = Field(None, description="PAN card number", examples=["ABCDE1234F"])
    addhar_number: Optional[str] = Field(None, description="Aadhaar card 12-digit number", examples=["987654321012"])

    model_config = ConfigDict(
        from_attributes=True,
    )


class AssignStoreRequest(BaseModel):
    store_id: int = Field(
        ...,
        gt=0,
        description="Store ID to assign to the user",
        examples=[1],
    )


class AssignStoreResponse(BaseModel):
    message: str = Field("Store assigned successfully", description="Status message", examples=["Store assigned successfully"])
    user_id: int = Field(..., description="User ID", examples=[1])
    store_id: int = Field(..., description="Assigned Store ID", examples=[1])
    store_name: Optional[str] = Field(None, description="Assigned Store Name", examples=["Downtown Branch"])
    role: Optional[str] = Field(None, description="User role name", examples=["cashier"])


class RemoveStoreRequest(BaseModel):
    store_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional Store ID to verify before removing user from store. If provided, ensures user is assigned to this store.",
        examples=[1],
    )


class RemoveStoreResponse(BaseModel):
    message: str = Field("User removed from store successfully", description="Status message", examples=["User removed from store successfully"])
    user_id: int = Field(..., description="User ID", examples=[1])
    store_id: Optional[int] = Field(None, description="New Store ID (null)", examples=[None])
    previous_store_id: Optional[int] = Field(None, description="Previously assigned Store ID", examples=[1])
    role: Optional[str] = Field(None, description="User role name", examples=["cashier"])


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
