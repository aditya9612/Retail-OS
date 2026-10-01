
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import re

from app.utils.phone import normalize_phone_number

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

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        if not value:
            return None
        return normalize_phone_number(value)

    @field_validator("owner_phone")
    @classmethod
    def validate_owner_phone(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        if not value:
            return None
        return normalize_phone_number(value)


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


class MobileOTPRequestSchema(BaseModel):
    """Request schema for POST /api/v1/auth/login/mobile-otp/request."""

    model_config = ConfigDict(str_strip_whitespace=True)

    domain: str = Field(..., min_length=1, description="Tenant domain identifier")
    phone: str = Field(..., description="Mobile phone number (Indian 10-digit format)")

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        val = value.strip().lower()
        if not val:
            raise ValueError("Domain is required")
        if not re.match(r"^[a-z0-9-]+$", val):
            raise ValueError("Domain must contain only lowercase alphanumeric characters and hyphens")
        return val

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Phone number is required")
        return normalize_phone_number(value)


class MobileOTPVerifySchema(BaseModel):
    """Request schema for POST /api/v1/auth/login/mobile-otp/verify."""

    model_config = ConfigDict(str_strip_whitespace=True)

    domain: str = Field(..., min_length=1, description="Tenant domain identifier")
    phone: str = Field(..., description="Mobile phone number (Indian 10-digit format)")
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        val = value.strip().lower()
        if not val:
            raise ValueError("Domain is required")
        if not re.match(r"^[a-z0-9-]+$", val):
            raise ValueError("Domain must contain only lowercase alphanumeric characters and hyphens")
        return val

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Phone number is required")
        return normalize_phone_number(value)

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("OTP must contain only digits")
        return value


class MobilePINLoginRequest(BaseModel):
    """Request schema for POST /api/v1/auth/login/mobile-pin."""

    model_config = ConfigDict(str_strip_whitespace=True)

    domain: str = Field(..., min_length=1, description="Tenant domain identifier")
    phone: str = Field(..., description="Mobile phone number (Indian 10-digit format)")
    pin: str = Field(..., min_length=4, max_length=4, description="4-digit security PIN")

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        val = value.strip().lower()
        if not val:
            raise ValueError("Domain is required")
        if not re.match(r"^[a-z0-9-]+$", val):
            raise ValueError("Domain must contain only lowercase alphanumeric characters and hyphens")
        return val

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Phone number is required")
        return normalize_phone_number(value)

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, value: str) -> str:
        val = str(value).strip()
        if len(val) != 4 or not val.isdigit():
            raise ValueError("PIN must be exactly 4 digits")
        return val


MobilePinLoginRequest = MobilePINLoginRequest


class PINSetupRequest(BaseModel):
    """Request schema for POST /api/v1/auth/pin/setup."""

    model_config = ConfigDict(str_strip_whitespace=True)

    pin: str = Field(..., min_length=4, max_length=4, description="4-digit security PIN")

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, value: str) -> str:
        val = str(value).strip()
        if len(val) != 4 or not val.isdigit():
            raise ValueError("PIN must be exactly 4 digits")
        return val


class PINChangeRequest(BaseModel):
    """Request schema for POST /api/v1/auth/pin/change."""

    model_config = ConfigDict(str_strip_whitespace=True)

    current_pin: str = Field(..., min_length=4, max_length=4, description="Current 4-digit security PIN")
    new_pin: str = Field(..., min_length=4, max_length=4, description="New 4-digit security PIN")

    @field_validator("current_pin")
    @classmethod
    def validate_current_pin(cls, value: str) -> str:
        val = str(value).strip()
        if len(val) != 4 or not val.isdigit():
            raise ValueError("Current PIN must be exactly 4 digits")
        return val

    @field_validator("new_pin")
    @classmethod
    def validate_new_pin(cls, value: str) -> str:
        val = str(value).strip()
        if len(val) != 4 or not val.isdigit():
            raise ValueError("New PIN must be exactly 4 digits")
        return val


class PINResetRequestSchema(BaseModel):
    """Request schema for POST /api/v1/auth/pin/reset/request."""

    model_config = ConfigDict(str_strip_whitespace=True)

    domain: str = Field(..., min_length=1, description="Tenant domain identifier")
    phone: str = Field(..., description="Mobile phone number (Indian 10-digit format)")

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        val = value.strip().lower()
        if not val:
            raise ValueError("Domain is required")
        if not re.match(r"^[a-z0-9-]+$", val):
            raise ValueError("Domain must contain only lowercase alphanumeric characters and hyphens")
        return val

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Phone number is required")
        return normalize_phone_number(value)


class PINResetVerifySchema(BaseModel):
    """Request schema for POST /api/v1/auth/pin/reset/verify."""

    model_config = ConfigDict(str_strip_whitespace=True)

    domain: str = Field(..., min_length=1, description="Tenant domain identifier")
    phone: str = Field(..., description="Mobile phone number (Indian 10-digit format)")
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        val = value.strip().lower()
        if not val:
            raise ValueError("Domain is required")
        if not re.match(r"^[a-z0-9-]+$", val):
            raise ValueError("Domain must contain only lowercase alphanumeric characters and hyphens")
        return val

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Phone number is required")
        return normalize_phone_number(value)

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("OTP must contain only digits")
        return value


class ResetPINRequest(BaseModel):
    """Request schema for POST /api/v1/auth/pin/reset."""

    model_config = ConfigDict(str_strip_whitespace=True)

    token: str = Field(..., min_length=1, description="Reset authorization token")
    new_pin: str = Field(..., min_length=4, max_length=4, description="New 4-digit security PIN")

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        val = value.strip()
        if not val:
            raise ValueError("Reset token is required")
        return val

    @field_validator("new_pin")
    @classmethod
    def validate_new_pin(cls, value: str) -> str:
        val = str(value).strip()
        if len(val) != 4 or not val.isdigit():
            raise ValueError("New PIN must be exactly 4 digits")
        return val

