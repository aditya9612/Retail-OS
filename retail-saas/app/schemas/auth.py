from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, TypeAdapter, field_validator


email_adapter = TypeAdapter(EmailStr)


class LoginRequest(BaseModel):
    email: str = Field(
        min_length=5,
        max_length=254,
        description="Valid email address. Email matching is case-sensitive.",
    )

    password: str = Field(
        min_length=6,
        max_length=100,
        description="Password must be at least 6 characters",
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("Email must not contain leading or trailing spaces")

        if not value:
            raise ValueError("Email is required")

        try:
            email_adapter.validate_python(value)
        except Exception:
            raise ValueError("Invalid email address")

        return value


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(
        min_length=10,
        description="Refresh token is required",
    )


class TokenPayload(BaseModel):
    sub: int
    tenant_id: int | None
    role: str
    exp: datetime


class ForgotPasswordRequest(BaseModel):
    email: str = Field(
        min_length=5,
        max_length=254,
        description="Registered user email address. Email matching is case-sensitive.",
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("Email must not contain leading or trailing spaces")

        if not value:
            raise ValueError("Email is required")

        try:
            email_adapter.validate_python(value)
        except Exception:
            raise ValueError("Invalid email address")

        return value


class ResetPasswordRequest(BaseModel):
    token: str = Field(
        min_length=20,
        description="Password reset token",
    )

    new_password: str = Field(
        min_length=8,
        max_length=100,
        description="New password",
    )