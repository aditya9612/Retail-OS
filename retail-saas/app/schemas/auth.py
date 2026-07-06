from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr = Field(description="Must be a valid email address")
    password: str = Field(min_length=6, max_length=100, description="Password must be at least 6 characters")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10, description="Refresh token is required")


class TokenPayload(BaseModel):
    sub: int
    tenant_id: int
    role: str
    exp: datetime