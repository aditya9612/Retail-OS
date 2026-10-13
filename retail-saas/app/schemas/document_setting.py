import re
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, field_validator
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
    invoice_prefix: str | None = None
    bill_prefix: str | None = None
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
    invoice_prefix: str = "INV"
    bill_prefix: str = "BILL"
    show_gstin: bool = True
    show_qr: bool = True
    show_signature: bool = False
    show_payment_details: bool = True
    logo_url: str | None = None


# Alias for backward compatibility
DocumentSetting = BrandingContext
