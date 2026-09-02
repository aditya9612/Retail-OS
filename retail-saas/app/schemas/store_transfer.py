from decimal import Decimal
from typing import List

from pydantic import BaseModel, Field


class StoreTransferItemCreate(BaseModel):
    product_id: int
    quantity: Decimal = Field(gt=0)


class StoreTransferCreate(BaseModel):
    source_store_id: int
    destination_store_id: int
    items: List[StoreTransferItemCreate] = Field(min_length=1)


class StoreTransferItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: Decimal

    class Config:
        from_attributes = True


class StoreTransferResponse(BaseModel):
    id: int
    transfer_number: str
    source_store_id: int
    destination_store_id: int
    status: str
    approved_by: int | None
    items: List[StoreTransferItemResponse]

    class Config:
        from_attributes = True