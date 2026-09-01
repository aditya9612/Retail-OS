from datetime import datetime

from pydantic import BaseModel, Field, field_validator


VALID_RETURN_STATUSES = [
    "requested",
    "approved",
    "rejected",
    "completed",
]


class OrderReturnCreate(BaseModel):
    order_id: int = Field(
        ...,
        gt=0,
        description="Order ID must be a positive integer",
    )

    customer_id: int = Field(
        ...,
        gt=0,
        description="Customer ID must be a positive integer",
    )

    reason: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Return reason is required and must be 3-100 characters",
    )

    remarks: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Return remarks are required and must be 3-500 characters",
    )

    @field_validator("reason", "remarks")
    @classmethod
    def validate_text_fields(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("This field cannot be empty")

        if value.lower() == "string":
            raise ValueError(
                "Please provide a valid value instead of 'string'"
            )

        return value
    

class OrderReturnUpdate(BaseModel):
    reason: str | None = Field(
        default=None,
        min_length=3,
        max_length=100,
        description="Return reason must be 3-100 characters",
    )

    remarks: str | None = Field(
        default=None,
        min_length=3,
        max_length=500,
        description="Return remarks must be 3-500 characters",
    )

    @field_validator("reason", "remarks")
    @classmethod
    def validate_update_fields(
        cls,
        value: str | None,
    ) -> str | None:

        if value is None:
            raise ValueError("This field cannot be null")

        value = value.strip()

        if not value:
            raise ValueError("This field cannot be empty")

        if value.lower() == "string":
            raise ValueError(
                "Please provide a valid value instead of 'string'"
            )

        return value


class OrderReturnStatusUpdate(BaseModel):
    status: str = Field(
        ...,
        min_length=1,
        max_length=30,
        description="Return status",
    )

    remarks: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Remarks are required and must be 3-500 characters",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        value = value.strip().lower()

        if not value:
            raise ValueError("Status cannot be empty")

        if value not in VALID_RETURN_STATUSES:
            raise ValueError(
                f"Invalid status. Allowed values: {VALID_RETURN_STATUSES}"
            )

        return value
    
    @field_validator("remarks")
    @classmethod
    def validate_remarks(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Remarks cannot be empty")

        if value.lower() == "string":
            raise ValueError(
                "Please provide a valid value instead of 'string'"
            )

        return value


class OrderReturnRejectRequest(BaseModel):
    remarks: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Rejection reason is required and must be 3-500 characters",
    )

    @field_validator("remarks")
    @classmethod
    def validate_rejection_remarks(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError(
                "Rejection remarks cannot be empty"
            )

        if value.lower() == "string":
            raise ValueError(
                "Please provide a valid value instead of 'string'"
            )

        return value
    

class OrderReturnResponse(BaseModel):
    id: int
    tenant_id: int
    order_id: int
    customer_id: int
    reason: str
    remarks: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }