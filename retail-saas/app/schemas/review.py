from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ReviewCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    product_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Product ID must be a positive integer",
    )

    store_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Store ID must be a positive integer",
    )

    customer_id: int = Field(
        ...,
        gt=0,
        description="Customer ID must be a positive integer",
    )

    order_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Order ID must be a positive integer",
    )

    rating: int = Field(
        ...,
        ge=1,
        le=5,
        description="Rating must be between 1 and 5",
    )

    comment: Optional[str] = Field(
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

    @model_validator(mode="after")
    def validate_target(self):
        if self.product_id is None and self.store_id is None:
            raise ValueError(
                "Either product_id or store_id must be provided"
            )
        return self


class ReviewUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    rating: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
        description="Rating must be between 1 and 5",
    )

    comment: Optional[str] = Field(
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


class ReviewReplyRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    merchant_reply: str = Field(
        ...,
        min_length=2,
        max_length=1000,
        description="Merchant reply to customer review",
    )

    @field_validator("merchant_reply")
    @classmethod
    def validate_reply(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Reply must contain at least 2 characters")
        if value.isdigit():
            raise ValueError("Reply cannot contain only numbers")
        return value


class ReviewStatusUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    status: str = Field(
        ...,
        description="Review moderation status (approved, pending, rejected, hidden)",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        allowed = {"approved", "pending", "rejected", "hidden"}
        value = value.strip().lower()
        if value not in allowed:
            raise ValueError(f"Status must be one of {allowed}")
        return value


class ReviewResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    tenant_id: int
    product_id: Optional[int] = None
    store_id: Optional[int] = None
    order_id: Optional[int] = None
    customer_id: int
    customer_name: Optional[str] = None
    product_name: Optional[str] = None
    store_name: Optional[str] = None
    rating: int
    comment: Optional[str] = None
    is_verified_purchase: bool = False
    status: str = "approved"
    is_edited: bool = False
    merchant_reply: Optional[str] = None
    replied_at: Optional[datetime] = None
    replied_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class RatingBreakdown(BaseModel):
    star_1: int = 0
    star_2: int = 0
    star_3: int = 0
    star_4: int = 0
    star_5: int = 0


class ReviewSummaryResponse(BaseModel):
    target_type: str  # "product" or "store"
    target_id: int
    total_reviews: int
    average_rating: float
    rating_breakdown: RatingBreakdown


class ReviewListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ReviewResponse]
