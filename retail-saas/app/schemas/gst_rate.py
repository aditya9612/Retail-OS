from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

VALID_GST_SLABS = [
    Decimal("0"),
    Decimal("0.25"),
    Decimal("1.5"),
    Decimal("3"),
    Decimal("5"),
    Decimal("12"),
    Decimal("18"),
    Decimal("28"),
]


class GstRateCreate(BaseModel):
    hsn_code: str = Field(min_length=4, max_length=8, description="HSN/SAC code must be 4 to 8 digits")
    gst_rate: Decimal = Field(ge=0, le=100, description="GST rate must be a valid slab: 0, 0.25, 1.5, 3, 5, 12, 18, 28")
    description: Optional[str] = Field(default=None, max_length=255, description="HSN/SAC goods or service description")
    code_type: Literal["HSN", "SAC"] = Field(default="HSN", description="Code type: HSN for goods, SAC for services")

    @field_validator("hsn_code")
    @classmethod
    def validate_hsn_code(cls, v: str) -> str:
        s = v.strip()
        if not s.isdigit():
            raise ValueError("HSN code must contain digits only")
        return s

    @field_validator("gst_rate")
    @classmethod
    def validate_gst_slab(cls, v: Decimal) -> Decimal:
        if v not in VALID_GST_SLABS:
            raise ValueError(f"GST rate must be one of {[str(s) for s in VALID_GST_SLABS]}")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "hsn_code": "6109",
                "gst_rate": "12.00",
                "description": "T-shirts, singlets and other knitted apparel",
                "code_type": "HSN",
            }
        }
    }


class GstRateUpdate(BaseModel):
    hsn_code: Optional[str] = Field(default=None, min_length=4, max_length=8, description="HSN code must be 4 to 8 digits")
    gst_rate: Optional[Decimal] = Field(default=None, ge=0, le=100, description="GST rate must be 0, 0.25, 1.5, 3, 5, 12, 18 or 28")
    description: Optional[str] = Field(default=None, max_length=255, description="HSN/SAC goods or service description")
    code_type: Optional[Literal["HSN", "SAC"]] = Field(default=None, description="Code type: HSN or SAC")
    status: Optional[bool] = None

    @field_validator("hsn_code")
    @classmethod
    def validate_hsn_code(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            s = v.strip()
            if not s.isdigit():
                raise ValueError("HSN code must contain digits only")
            return s
        return v

    @field_validator("gst_rate")
    @classmethod
    def validate_gst_slab(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v not in VALID_GST_SLABS:
            raise ValueError(f"GST rate must be one of {[str(s) for s in VALID_GST_SLABS]}")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "hsn_code": "6109",
                "gst_rate": "18.00",
                "description": "Updated apparel tax slab",
                "code_type": "HSN",
                "status": True,
            }
        }
    }


class GstRateResponse(BaseModel):
    id: int
    tenant_id: int
    hsn_code: str
    description: Optional[str] = None
    code_type: str = "HSN"
    gst_rate: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    status: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    supply_type: Optional[Literal["intra_state", "inter_state"]] = None

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": 1,
                "tenant_id": 1,
                "hsn_code": "6109",
                "description": "T-shirts, singlets and other knitted apparel",
                "code_type": "HSN",
                "gst_rate": "12.00",
                "cgst": "6.00",
                "sgst": "6.00",
                "igst": "12.00",
                "status": True,
                "created_at": "2026-10-23T10:00:00Z",
                "updated_at": "2026-10-23T10:00:00Z",
                "supply_type": "intra_state",
            }
        },
    }


class GstRateListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[GstRateResponse]


class GstSeedResponse(BaseModel):
    message: str
    seeded_count: int
    existing_count: int
    rates: list[GstRateResponse]


class GstBulkImportItem(BaseModel):
    hsn_code: str = Field(min_length=4, max_length=8, description="HSN/SAC code (4 to 8 digits)")
    gst_rate: Decimal = Field(ge=0, le=100, description="GST slab rate: 0, 0.25, 1.5, 3, 5, 12, 18, 28")
    description: Optional[str] = Field(default=None, max_length=255)
    code_type: Literal["HSN", "SAC"] = Field(default="HSN")

    @field_validator("hsn_code")
    @classmethod
    def validate_hsn_code(cls, v: str) -> str:
        s = v.strip()
        if not s.isdigit():
            raise ValueError("HSN code must contain digits only")
        return s

    @field_validator("gst_rate")
    @classmethod
    def validate_gst_slab(cls, v: Decimal) -> Decimal:
        if v not in VALID_GST_SLABS:
            raise ValueError(f"GST rate must be one of {[str(s) for s in VALID_GST_SLABS]}")
        return v


class GstBulkImportRequest(BaseModel):
    items: list[GstBulkImportItem] = Field(..., min_length=1, description="List of HSN/SAC rate items to import")

    model_config = {
        "json_schema_extra": {
            "example": {
                "items": [
                    {"hsn_code": "0401", "gst_rate": "0.00", "description": "Fresh milk & dairy", "code_type": "HSN"},
                    {"hsn_code": "1006", "gst_rate": "5.00", "description": "Rice & grains", "code_type": "HSN"},
                    {"hsn_code": "6109", "gst_rate": "12.00", "description": "T-shirts & apparel", "code_type": "HSN"},
                    {"hsn_code": "7113", "gst_rate": "3.00", "description": "Gold & jewellery", "code_type": "HSN"},
                    {"hsn_code": "7102", "gst_rate": "0.25", "description": "Precious diamonds", "code_type": "HSN"},
                    {"hsn_code": "8471", "gst_rate": "18.00", "description": "Computers & laptops", "code_type": "HSN"},
                    {"hsn_code": "9983", "gst_rate": "18.00", "description": "IT & consulting services", "code_type": "SAC"},
                ]
            }
        }
    }


class GstBulkImportResponse(BaseModel):
    message: str
    created_count: int
    updated_count: int
    errors: list[str] = []
    rates: list[GstRateResponse]
