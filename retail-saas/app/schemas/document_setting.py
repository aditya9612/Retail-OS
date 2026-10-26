import re
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.utils.validators import (
    validate_email_address,
    validate_gstin_number,
    validate_website_url,
    validate_indian_phone,
)


class DocumentSettingBase(BaseModel):
    business_name: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    gstin: str | None = None
    footer_text: str | None = None
    terms_and_conditions: str | None = None
    invoice_prefix: str | None = None
    bill_prefix: str | None = None
    padding_length: int = Field(default=6, ge=4, le=10, description="Serial sequence padding digits (4 to 10)")
    primary_color: str | None = Field(default=None, description="Primary brand HEX color code e.g. #1E3A8A")
    secondary_color: str | None = Field(default=None, description="Secondary brand HEX color code e.g. #059669")
    show_gstin: bool = True
    show_qr: bool = True
    show_signature: bool = False
    show_payment_details: bool = True
    logo_path: str | None = None

    @field_validator("email")
    @classmethod
    def validate_branding_email(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        return validate_email_address(v, field_name="Branding email", required=False)

    @field_validator("phone")
    @classmethod
    def validate_branding_phone(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        v_str = str(v).strip()
        if v_str.lower() in ("string", "null", "none", "undefined"):
            raise ValueError("Branding phone cannot be placeholder")
        clean = re.sub(r"[\s\-\(\)\.]", "", v_str)
        if re.fullmatch(r"^(?:\+91)?[6-9]\d{9}$", clean):
            return clean
        digits = re.sub(r"^(?:\+91|0)", "", clean)
        if digits.isdigit() and (8 <= len(digits) <= 11):
            return clean
        raise ValueError(
            "Branding phone must be a 10-digit Indian mobile number starting with 6-9, or a landline number with STD code"
        )

    @field_validator("gstin")
    @classmethod
    def validate_branding_gstin(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        return validate_gstin_number(v, field_name="Branding GSTIN", required=False)

    @field_validator("website")
    @classmethod
    def validate_branding_website(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        return validate_website_url(v, field_name="Branding website", required=False)

    @field_validator("invoice_prefix", "bill_prefix")
    @classmethod
    def validate_prefix(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        v = v.strip().upper()
        if not re.fullmatch(r"^[A-Z0-9\-_]{2,10}$", v):
            raise ValueError("Prefix must be 2-10 alphanumeric characters, hyphens or underscores")
        return v

    @field_validator("primary_color", "secondary_color")
    @classmethod
    def validate_hex_color(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        v = v.strip().upper()
        if not re.fullmatch(r"^#([A-F0-9]{6}|[A-F0-9]{3})$", v):
            raise ValueError("Color must be a valid HEX color code e.g. #1E3A8A")
        return v


class DocumentSettingCreate(DocumentSettingBase):
    pass


class DocumentSettingUpdate(DocumentSettingBase):
    pass


class DocumentSettingResponse(DocumentSettingBase):
    id: int
    tenant_id: int
    store_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("phone", "email", "gstin", "website", mode="plain", check_fields=False)
    @classmethod
    def allow_existing_branding_fields(cls, v: Any) -> Any:
        return v


class BrandingContext(BaseModel):
    business_name: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    gstin: str = ""
    footer_text: str = ""
    terms_and_conditions: str = ""
    invoice_prefix: str = "INV"
    bill_prefix: str = "BILL"
    padding_length: int = 6
    primary_color: str = "#1E3A8A"
    secondary_color: str = "#059669"
    show_gstin: bool = True
    show_qr: bool = True
    show_signature: bool = False
    show_payment_details: bool = True
    logo_url: str | None = None


# Alias for backward compatibility
DocumentSetting = BrandingContext
