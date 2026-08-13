from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr = Field(
        description="Must be a valid email address"
    )

    password: str = Field(
        min_length=6,
        max_length=100,
        description="Password must be at least 6 characters",
    )


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
    tenant_id: int
    role: str
    exp: datetime


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(
        description="Registered user email address",
    )


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