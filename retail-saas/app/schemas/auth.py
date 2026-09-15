from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, TypeAdapter, field_validator


email_adapter = TypeAdapter(EmailStr)


def normalize_email(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(
            "Email must be a string"
        )

    value = value.strip()

    if not value:
        raise ValueError(
            "Email is required"
        )

    if len(value) > 254:
        raise ValueError(
            "Email must not exceed 254 characters"
        )

    try:
        normalized = str(
            email_adapter.validate_python(value)
        )
    except Exception as exc:
        raise ValueError(
            "Invalid email address"
        ) from exc

    return normalized.lower()


def validate_password_value(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(
            "Password must be a string"
        )

    if not value:
        raise ValueError(
            "Password is required"
        )

    if not value.strip():
        raise ValueError(
            "Password cannot contain only whitespace"
        )

    if len(value) < 8:
        raise ValueError(
            "Password must be at least 8 characters"
        )

    if len(value) > 100:
        raise ValueError(
            "Password must not exceed 100 characters"
        )

    if not any(
        character.isupper()
        for character in value
    ):
        raise ValueError(
            "Password must contain at least one uppercase letter"
        )

    if not any(
        character.islower()
        for character in value
    ):
        raise ValueError(
            "Password must contain at least one lowercase letter"
        )

    if not any(
        character.isdigit()
        for character in value
    ):
        raise ValueError(
            "Password must contain at least one number"
        )

    if not any(
        not character.isalnum()
        for character in value
    ):
        raise ValueError(
            "Password must contain at least one special character"
        )

    return value


class LoginRequest(BaseModel):
    email: str = Field(
        min_length=5,
        max_length=254,
        description="Email address.",
    )

    password: str = Field(
        min_length=8,
        max_length=100,
        description="Password.",
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_value(value)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(
        min_length=10,
        description="Refresh token is required.",
    )

    @field_validator("refresh_token")
    @classmethod
    def validate_refresh_token(
        cls,
        value: str,
    ) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Refresh token is required"
            )

        return value


class TokenPayload(BaseModel):
    sub: int
    tenant_id: int | None
    role: str
    exp: datetime


class LogoutRequest(BaseModel):
    token: str = Field(
        min_length=20,
        max_length=500,
        description="Access or refresh token.",
    )

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Token is required"
            )

        return value


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(
        min_length=8,
        max_length=100,
    )

    new_password: str = Field(
        min_length=8,
        max_length=100,
    )

    confirm_password: str = Field(
        min_length=8,
        max_length=100,
    )

    @field_validator(
        "old_password",
        "new_password",
        "confirm_password",
    )
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_value(value)

    @field_validator("confirm_password")
    @classmethod
    def validate_confirmation(
        cls,
        value: str,
        info,
    ) -> str:
        new_password = info.data.get(
            "new_password"
        )

        if (
            new_password is not None
            and value != new_password
        ):
            raise ValueError(
                "New password and confirm password must match"
            )

        return value


class ForgotPasswordRequest(BaseModel):
    email: str = Field(
        min_length=5,
        max_length=254,
        description="Registered user email address.",
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class VerifyOTPRequest(BaseModel):
    email: str = Field(
        min_length=5,
        max_length=254,
    )

    otp: str = Field(
        min_length=6,
        max_length=6,
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, value: str) -> str:
        value = value.strip()

        if not value.isdigit():
            raise ValueError(
                "OTP must contain only digits"
            )

        if len(value) != 6:
            raise ValueError(
                "OTP must be exactly 6 digits"
            )

        return value


class ResetPasswordRequest(BaseModel):
    token: str = Field(
        min_length=20,
        max_length=500,
    )

    new_password: str = Field(
        min_length=8,
        max_length=100,
    )

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Reset token is required"
            )

        return value

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_value(value)