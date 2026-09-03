from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ReviewCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    product_id: int = Field(
        ...,
        gt=0,
        description="Product ID must be a positive integer",
    )

    customer_id: int = Field(
        ...,
        gt=0,
        description="Customer ID must be a positive integer",
    )

    rating: int = Field(
        ...,
        ge=1,
        le=5,
        description="Rating must be between 1 and 5",
    )

    comment: str | None = Field(
        default=None,
        max_length=1000,
    )

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        if len(value) < 2:
            raise ValueError(
                "Comment must contain at least 2 characters"
            )

        if value.isdigit():
            raise ValueError(
                "Comment cannot contain only numbers"
            )

        return value


class ReviewUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    rating: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Rating must be between 1 and 5",
    )

    comment: str | None = Field(
        default=None,
        max_length=1000,
    )

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError(
                "Comment cannot be empty"
            )

        if len(value) < 2:
            raise ValueError(
                "Comment must contain at least 2 characters"
            )

        if value.isdigit():
            raise ValueError(
                "Comment cannot contain only numbers"
            )

        return value

    @model_validator(mode="after")
    def validate_at_least_one_field(self):
        if self.rating is None and self.comment is None:
            raise ValueError(
                "At least one field must be provided for update"
            )

        return self


class ReviewResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    tenant_id: int
    product_id: int
    customer_id: int
    rating: int
    comment: str | None
    created_at: datetime
    updated_at: datetime