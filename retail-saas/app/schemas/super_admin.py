from datetime import datetime
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


class SuperAdminCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(
        ...,
        min_length=2,
        max_length=255,
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )
    phone: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: EmailStr) -> str:
        value = str(value).strip()

        if not value:
            raise ValueError(
                "Email cannot be empty"
            )

        return value

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Full name cannot be empty"
            )

        if len(value) < 2:
            raise ValueError(
                "Full name must contain at least 2 characters"
            )

        if not re.fullmatch(
            r"[A-Za-z][A-Za-z .'-]*",
            value,
        ):
            raise ValueError(
                "Full name can contain only letters, spaces, dots, apostrophes and hyphens"
            )

        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError(
                "Password cannot start or end with whitespace"
            )

        if any(char.isspace() for char in value):
            raise ValueError(
                "Password cannot contain whitespace"
            )

        if not re.search(r"[A-Z]", value):
            raise ValueError(
                "Password must contain at least one uppercase letter"
            )

        if not re.search(r"[a-z]", value):
            raise ValueError(
                "Password must contain at least one lowercase letter"
            )

        if not re.search(r"\d", value):
            raise ValueError(
                "Password must contain at least one number"
            )

        if not re.search(
            r"[^A-Za-z0-9]",
            value,
        ):
            raise ValueError(
                "Password must contain at least one special character"
            )

        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not re.fullmatch(
            r"[6-9]\d{9}",
            value,
        ):
            raise ValueError(
                "Phone must be a valid 10-digit Indian mobile number starting with 6, 7, 8 or 9"
            )

        return value


class SuperAdminLogin(BaseModel):
    email: EmailStr
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: EmailStr) -> str:
        value = str(value).strip()

        if not value:
            raise ValueError(
                "Email cannot be empty"
            )

        return value


class SuperAdminUpdate(BaseModel):
    full_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=255,
    )
    phone: str | None = None
    email: EmailStr | None = None

    @field_validator("email")
    @classmethod
    def validate_email(
        cls,
        value: EmailStr | None,
    ) -> str | None:
        if value is None:
            return None

        value = str(value).strip()

        if not value:
            raise ValueError(
                "Email cannot be empty"
            )

        return value

    @field_validator("full_name")
    @classmethod
    def validate_full_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "Full name cannot be empty"
            )

        if not re.fullmatch(
            r"[A-Za-z][A-Za-z .'-]*",
            value,
        ):
            raise ValueError(
                "Full name can contain only letters, spaces, dots, apostrophes and hyphens"
            )

        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not re.fullmatch(
            r"[6-9]\d{9}",
            value,
        ):
            raise ValueError(
                "Phone must be a valid 10-digit Indian mobile number starting with 6, 7, 8 or 9"
            )

        return value


class SuperAdminStatusUpdate(BaseModel):
    is_active: bool


class SuperAdminChangePassword(BaseModel):
    current_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )

    @field_validator("new_password")
    @classmethod
    def validate_new_password(
        cls,
        value: str,
    ) -> str:
        if value != value.strip():
            raise ValueError(
                "Password cannot start or end with whitespace"
            )

        if any(char.isspace() for char in value):
            raise ValueError(
                "Password cannot contain whitespace"
            )

        if not re.search(r"[A-Z]", value):
            raise ValueError(
                "Password must contain at least one uppercase letter"
            )

        if not re.search(r"[a-z]", value):
            raise ValueError(
                "Password must contain at least one lowercase letter"
            )

        if not re.search(r"\d", value):
            raise ValueError(
                "Password must contain at least one number"
            )

        if not re.search(
            r"[^A-Za-z0-9]",
            value,
        ):
            raise ValueError(
                "Password must contain at least one special character"
            )

        return value


class SuperAdminResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    email: EmailStr
    full_name: str
    phone: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SuperAdminTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class SuperAdminTenantResponse(BaseModel):
    id: int
    name: str
    slug: str
    email: str | None = None
    phone: str | None = None
    is_active: bool | None = None

    model_config = ConfigDict(
        from_attributes=True
    )


class TenantStatusUpdate(BaseModel):
    is_active: bool


class SuperAdminTenantUserResponse(BaseModel):
    id: int
    tenant_id: int
    email: EmailStr
    full_name: str
    phone: str | None = None
    is_active: bool

    model_config = ConfigDict(
        from_attributes=True
    )


class SuperAdminDashboardResponse(BaseModel):
    total_super_admins: int
    active_super_admins: int
    inactive_super_admins: int
    total_tenants: int
    active_tenants: int
    inactive_tenants: int
    total_users: int