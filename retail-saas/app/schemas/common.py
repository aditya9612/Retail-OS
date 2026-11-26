from typing import Generic, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")
C = TypeVar("C")


class BasicStatusCounts(BaseModel):
    """Standard active/inactive summary counts."""

    total: int = 0
    active: int = 0
    inactive: int = 0


class TotalCountOnly(BaseModel):
    """Summary count when items only have a total count."""

    total: int = 0


class ListWithCountsResponse(BaseModel, Generic[T, C]):
    """Standard paginated list response with summary counts for UI display."""

    success: bool = True
    message: str = "Retrieved successfully"
    items: list[T] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 1
    counts: C

    model_config = ConfigDict(from_attributes=True)
