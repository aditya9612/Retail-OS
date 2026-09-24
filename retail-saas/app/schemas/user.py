
from datetime import datetime
from typing import Optional
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


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
    )

    role_id: int = Field(
        gt=0,
        description="Role ID from GET /api/v1/users/roles. The role must belong to the current tenant.",
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: EmailStr) -> str:
        value = str(value).strip().lower()

        if not value:
            raise ValueError("Email cannot be empty")

        if len(value) > 255:
            raise ValueError("Email cannot exceed 255 characters")

        local_part, separator, domain = value.rpartition("@")

        if not separator or not local_part or not domain:
            raise ValueError("Invalid email address")

        if "." not in domain:
            raise ValueError(
                "Email domain must contain a valid domain extension"
            )

        if (
            domain.startswith(".")
            or domain.endswith(".")
            or ".." in domain
        ):
            raise ValueError("Invalid email domain")

        return value

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

        if value is None:
            return None

        value = str(value).strip()

        if not value:
            raise ValueError("Phone cannot be empty")

        if not PHONE_PATTERN.fullmatch(value):
            raise ValueError(
                "Phone must be 10 digits starting with 6-9 or +91 followed by 10 digits"
            )

        if value.startswith("+91"):
            value = value[3:]

        return value


class UserCreate(UserBase):

    password: str = Field(
        min_length=8,
        max_length=100,
    )

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
        description="Role ID from GET /api/v1/users/roles.",
    )

    is_active: Optional[bool] = None

    password: Optional[str] = Field(
        default=None,
        min_length=8,
        max_length=100,
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

        if value is None:
            return None

        value = str(value).strip()

        if not value:
            raise ValueError("Phone cannot be empty")

        if not PHONE_PATTERN.fullmatch(value):
            raise ValueError(
                "Phone must be 10 digits starting with 6-9 or +91 followed by 10 digits"
            )

        if value.startswith("+91"):
            value = value[3:]

        return value

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

        if value is None:
            return None

        value = str(value).strip()

        if not value:
            raise ValueError("Phone cannot be empty")

        if not PHONE_PATTERN.fullmatch(value):
            raise ValueError(
                "Phone must be 10 digits starting with 6-9 or +91 followed by 10 digits"
            )

        if value.startswith("+91"):
            value = value[3:]

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

    model_config = ConfigDict(
        from_attributes=True,
    )


class StoreBase(BaseModel):

    name: str = Field(
        min_length=2,
        max_length=255,
    )

    code: str = Field(
        min_length=1,
        max_length=20,
    )

    address: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    city: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    state: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    pincode: Optional[str] = Field(
        default=None,
        min_length=6,
        max_length=6,
    )

    phone: Optional[str] = Field(
        default=None,
        min_length=10,
        max_length=15,
    )

    gstin: Optional[str] = Field(
        default=None,
        min_length=15,
        max_length=15,
    )

    is_warehouse: bool = False

    @field_validator(
        "name",
        "code",
        "address",
        "city",
        "state",
    )
    @classmethod
    def validate_text(
        cls,
        value: Optional[str],
    ) -> Optional[str]:

        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Field cannot be empty")

        return value

    @field_validator("pincode")
    @classmethod
    def validate_pincode(
        cls,
        value: Optional[str],
    ) -> Optional[str]:

        if value is None:
            return None

        if not value.isdigit():
            raise ValueError("Pincode must contain digits only")

        if len(value) != 6:
            raise ValueError(
                "Pincode must contain exactly 6 digits"
            )

        return value

    @field_validator("phone")
    @classmethod
    def validate_store_phone(
        cls,
        value: Optional[str],
    ) -> Optional[str]:

        if value is None:
            return None

        if not value.isdigit():
            raise ValueError("Phone must contain digits only")

        if len(value) < 10 or len(value) > 15:
            raise ValueError(
                "Phone must contain 10 to 15 digits"
            )

        return value

    @field_validator("gstin")
    @classmethod
    def validate_gstin(
        cls,
        value: Optional[str],
    ) -> Optional[str]:

        if value is None:
            return None

        value = value.strip().upper()

        if len(value) != 15:
            raise ValueError(
                "GSTIN must contain exactly 15 characters"
            )

        if not value.isalnum():
            raise ValueError(
                "GSTIN must contain only letters and digits"
            )

        return value


class StoreCreate(StoreBase):
    pass


class StoreUpdate(BaseModel):

    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=255,
    )

    address: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    city: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    state: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    pincode: Optional[str] = Field(
        default=None,
        min_length=6,
        max_length=6,
    )

    phone: Optional[str] = Field(
        default=None,
        min_length=10,
        max_length=15,
    )

    gstin: Optional[str] = Field(
        default=None,
        min_length=15,
        max_length=15,
    )

    is_active: Optional[bool] = None

    is_warehouse: Optional[bool] = None

    @model_validator(mode="after")
    def validate_update(self):

        if not self.model_fields_set:
            raise ValueError(
                "At least one field must be provided for update"
            )

        return self
