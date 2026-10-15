from datetime import datetime
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

    if len(v) < 3 or len(v) > 255:
        raise ValueError("Category name must be between 3 and 255 characters")

    if v.lower() in PLACEHOLDER_VALUES:
        raise ValueError(f"Category name cannot be placeholder '{v}'")

    # Check for dangerous HTML / script content
    if re.search(r"<\s*script|javascript\s*:|onload\s*=", v, re.IGNORECASE):
        raise ValueError("Category name contains invalid script content")

    # Only allow letters, numbers, spaces, and safe retail connectors ('&', '-')
    # Strictly reject random symbols (!@#$, [], {}, (), ,, //, \\, ||, <<, >>, ??, etc.)
    if not re.fullmatch(r"^[a-zA-Z0-9\s\-&]+$", v):
        raise ValueError("Category name contains invalid characters. Only letters, numbers, spaces, and '&' or '-' are allowed")

    # Reject consecutive symbols like '--' or '&&'
    if "--" in v or "&&" in v:
        raise ValueError("Category name cannot contain consecutive symbols like '--' or '&&'")

    # Cannot start or end with a symbol
    if v.startswith(("-", "&")) or v.endswith(("-", "&")):
        raise ValueError("Category name cannot start or end with a symbol")

    # Reject if numeric-only (e.g., "1234", "999")
    if v.isdigit() or bool(re.fullmatch(r"^\d+$", v)):
        raise ValueError("Category name cannot consist only of numbers")

    # Must contain at least 2 alphabetic characters
    alpha_count = sum(1 for c in v if c.isalpha())
    if alpha_count < 2:
        raise ValueError("Category name must contain at least 2 alphabetic letters")

    # Reject repeating identical characters (e.g., "PP", "AAA", "xxxx", "ZZZZ")
    cleaned = re.sub(r"[\s\-_&0-9]", "", v)
    if len(cleaned) > 1 and len(set(cleaned.lower())) == 1:
        raise ValueError("Category name cannot consist of repeating identical characters")

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

    # Check for dangerous HTML / script content
    if re.search(r"<\s*script|javascript\s*:|onload\s*=", v, re.IGNORECASE):
        raise ValueError("Description contains invalid script content")

    # Only allow letters, numbers, spaces, and standard sentence punctuation (.,'\"&()\-/:;%)
    # Strictly reject random symbols like @, #, $, ^, *, ~, |, <, >, {, }, etc.
    if not re.fullmatch(r"^[a-zA-Z0-9\s.,'\"&()\-/:;%]+$", v):
        raise ValueError("Description contains invalid characters. Random symbols like '@', '#', '$' are not allowed")

    # Reject if numeric-only (e.g., "1234", "999")
    if v.isdigit() or bool(re.fullmatch(r"^\d+$", v)):
        raise ValueError("Description cannot consist only of numbers")

    # Must contain at least 3 alphabetic characters
    alpha_count = sum(1 for c in v if c.isalpha())
    if alpha_count < 3:
        raise ValueError("Description must contain at least 3 alphabetic letters")

    # Reject repeating identical characters (e.g., "aaaaa", "00000")
    cleaned = re.sub(r"[\s\-_.,/()0-9]", "", v)
    if len(cleaned) > 1 and len(set(cleaned.lower())) == 1:
        raise ValueError("Description cannot consist of repeating identical characters")

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
            raise ValueError("Category name cannot be null")
        return validate_category_name(value)

    @field_validator("description")
    @classmethod
    def validate_desc(cls, value: Optional[str]) -> Optional[str]:
        return validate_category_description(value)


class CategoryResponse(BaseModel):
    id: int
    tenant_id: int
    parent_id: int | None = None
    name: str
    is_active: bool = True
    description: str | None = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CategoryDetailResponse(CategoryResponse):
    parent_name: str | None = None
    product_count: int = 0
    subcategory_count: int = 0


class CategoryDetailWrapperResponse(BaseModel):
    success: bool = True
    message: str = "Category details retrieved successfully"
    data: CategoryDetailResponse


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
