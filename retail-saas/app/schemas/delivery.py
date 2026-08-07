from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DeliveryStatusUpdate(BaseModel):
    status: str = Field(
        description="Delivery status",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str):
        allowed = {
            "pending",
            "assigned",
            "out_for_delivery",
            "delivered",
            "cancelled",
        }

        if value not in allowed:
            raise ValueError(
                "Status must be pending, assigned, out_for_delivery, delivered or cancelled"
            )

        return value


class DeliveryResponse(BaseModel):
    id: int
    tenant_id: int
    order_id: int
    status: str
    delivery_person: str | None
    tracking_number: str | None
    delivered_at: datetime | None
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }