
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import re

EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
)


def normalize_email(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Email address is required")
    if not EMAIL_PATTERN.fullmatch(value):
        raise ValueError("Invalid email address")
    return value


def validate_password_value(value: str) -> str:
    if not value:
        raise ValueError("Password is required")
    if len(value) < 6:
        raise ValueError("Password must be at least 6 characters")
    if len(value) > 128:
        raise ValueError("Password must not exceed 128 characters")
    return value


class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, populate_by_name=True)

    tenant_name: str = Field(..., min_length=2, max_length=255, description="Tenant/Store name")
    domain: str = Field(..., min_length=2, max_length=255, description="Tenant unique domain identifier")
    email: str = Field(..., description="Administrator/Owner email address")
    admin_name: str = Field(..., min_length=2, max_length=255, description="Administrator/Owner full name")
    password: str = Field(..., description="Administrator/Owner password")
    phone: str | None = Field(default=None, description="Administrator/Owner phone number")
    plan_id: int | None = Field(default=None, description="Optional subscription plan ID")
    plan_code: str | None = Field(default=None, description="Optional subscription plan code")

    # Store Owner aliases
    store_name: Optional[str] = None
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None
    owner_phone: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def populate_store_owner_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("tenant_name") and data.get("store_name"):
                data["tenant_name"] = data["store_name"]
            if not data.get("admin_name") and data.get("owner_name"):
                data["admin_name"] = data["owner_name"]
            if not data.get("email") and data.get("owner_email"):
                data["email"] = data["owner_email"]
            if not data.get("phone") and data.get("owner_phone"):
                data["phone"] = data["owner_phone"]
        return data

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_value(value)

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        val = value.strip().lower()
        if not re.match(r"^[a-z0-9-]+$", val):
            raise ValueError("Domain must contain only lowercase alphanumeric characters and hyphens")
        return val


class RegisterResponse(BaseModel):
    message: str = "Tenant registered"
    user_id: int
    tenant_id: int


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_value(value)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    refresh_token: str

    @field_validator("refresh_token")
    @classmethod
    def validate_refresh_token(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Refresh token is required")
        return value


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class VerifyOTPRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str
    otp: str = Field(min_length=6, max_length=6)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("OTP must contain only digits")
        return value


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    token: str
    new_password: str

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Reset token is required")
        return value

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return validate_password_value(value)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    old_password: str
    new_password: str
    confirm_password: str

    @field_validator("old_password")
    @classmethod
    def validate_old_password(cls, value: str) -> str:
        if not value:
            raise ValueError("Current password is required")
        return value

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return validate_password_value(value)

    @field_validator("confirm_password")
    @classmethod
    def validate_confirm_password(cls, value: str) -> str:
        if not value:
            raise ValueError("Confirm password is required")
        return value
