
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def normalize_email(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("Email address is required")

    try:
        normalized = str(EmailStr(value))
    except Exception as exc:
        raise ValueError("Invalid email address") from exc

    return normalized


def validate_password_value(value: str) -> str:
    if not value:
        raise ValueError("Password is required")

    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters")

    if len(value) > 128:
        raise ValueError("Password must not exceed 128 characters")

    if not any(char.isupper() for char in value):
        raise ValueError("Password must contain at least one uppercase letter")

    if not any(char.islower() for char in value):
        raise ValueError("Password must contain at least one lowercase letter")

    if not any(char.isdigit() for char in value):
        raise ValueError("Password must contain at least one digit")

    if not any(not char.isalnum() for char in value):
        raise ValueError("Password must contain at least one special character")

    return value


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
