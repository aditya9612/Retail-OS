import re
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


PLACEHOLDER_VALUES = {
    "string",
    "null",
    "none",
    "undefined",
    "----",
    "---",
    "--",
    "- - -",
    "@#$%^",
    "!@#$%",
    "test",
    "sample",
    "temp",
    "n/a",
    "na",
}


def validate_category_name(v: str) -> str:
    if v is None:
        raise ValueError("Category name cannot be null")
    if not isinstance(v, str):
        raise ValueError("Category name must be a string")

    v = v.strip()
    if not v:
        raise ValueError("Category name cannot be empty or whitespace")

    if len(v) < 2 or len(v) > 255:
        raise ValueError("Category name must be between 2 and 255 characters")

    if v.lower() in PLACEHOLDER_VALUES:
        raise ValueError(f"Category name cannot be placeholder '{v}'")

    # Reject if only special characters or repeating symbols
    if re.fullmatch(r"^[-_.@#$%^&*!+=~`|<>?/\\]+$", v):
        raise ValueError("Category name cannot consist only of special characters")

    # Reject if numeric-only (e.g., "1234", "999")
    if v.isdigit() or re.fullmatch(r"^\d+$", v):
        raise ValueError("Category name cannot consist only of numbers")

    # Must contain at least one letter (allows real-world names like "4K TVs", "Shoes 2026", "USB-C Accessories")
    if not any(c.isalpha() for c in v):
        raise ValueError("Category name must contain at least one letter")

    # Check for dangerous HTML / script content
    if re.search(r"<\s*script|javascript\s*:|onload\s*=", v, re.IGNORECASE):
        raise ValueError("Category name contains invalid script content")

    return v


def validate_category_description(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValueError("Description must be a string")

    v = v.strip()
    if not v:
        raise ValueError("Description cannot be empty or whitespace")

    if len(v) < 3 or len(v) > 500:
        raise ValueError("Description must be between 3 and 500 characters")

    if v.lower() in PLACEHOLDER_VALUES:
        raise ValueError(f"Description cannot be placeholder '{v}'")

    # Reject if only special characters
    if re.fullmatch(r"^[-_.@#$%^&*!+=~`|<>?/\\]+$", v):
        raise ValueError("Description cannot consist only of special characters")

    # Reject if numeric-only
    if v.isdigit() or re.fullmatch(r"^\d+$", v):
        raise ValueError("Description cannot consist only of numbers")

    # Must contain at least one letter
    if not any(c.isalpha() for c in v):
        raise ValueError("Description must contain at least one letter")

    # Check for dangerous HTML / script content
    if re.search(r"<\s*script|javascript\s*:|onload\s*=", v, re.IGNORECASE):
        raise ValueError("Description contains invalid script content")

    return v


class CategoryCreate(BaseModel):
    name: str
    is_active: bool = True
    description: Optional[str] = None
    parent_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Parent category ID must be greater than 0",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_category_name(value)

    @field_validator("description")
    @classmethod
    def validate_desc(cls, value: Optional[str]) -> Optional[str]:
        return validate_category_description(value)


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None
    parent_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Parent category ID must be greater than 0",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return validate_category_name(value)

    @field_validator("description")
    @classmethod
    def validate_desc(cls, value: Optional[str]) -> Optional[str]:
        return validate_category_description(value)


class CategoryResponse(BaseModel):
    id: int
    tenant_id: int
    parent_id: int | None
    name: str
    is_active: bool = True
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CategoryListResponse(BaseModel):
    success: bool = True
    message: str
    data: list[CategoryResponse] = Field(default_factory=list)


class CategoryDeleteData(BaseModel):
    id: int


class CategoryDeleteResponse(BaseModel):
    success: bool = True
    message: str = "Category deleted successfully"
    data: CategoryDeleteData