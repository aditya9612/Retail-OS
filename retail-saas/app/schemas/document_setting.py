import re
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.utils.validators import (
    validate_email_address,
    validate_gstin_number,
    validate_website_url,
    validate_indian_phone,
)


class DocumentSettingBase(BaseModel):
    business_name: Optional[str] = Field(default=None, max_length=255, description="Legal business or store display name")
    address: Optional[str] = Field(default=None, max_length=500, description="Physical store or registered company address")
    phone: Optional[str] = Field(default=None, max_length=25, description="Contact phone (10-digit Indian mobile starting with 6-9 or landline with STD code)")
    email: Optional[EmailStr] = Field(default=None, description="Official business or billing email address")
    website: Optional[str] = Field(default=None, max_length=255, description="Business website URL (e.g. https://www.example.com)")
    gstin: Optional[str] = Field(default=None, min_length=15, max_length=15, pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$", description="Valid 15-character GSTIN number (e.g. 27AAPCA1234A1Z5)")
    footer_text: Optional[str] = Field(default=None, max_length=500, description="Custom thank-you note printed at the bottom of bills/invoices")
    terms_and_conditions: Optional[str] = Field(default=None, max_length=2000, description="Terms and conditions printed on invoices (e.g. return policy)")
    invoice_prefix: Optional[str] = Field(default=None, max_length=10, description="Invoice sequence prefix (2-10 uppercase alphanumeric, e.g. INV)")
    bill_prefix: Optional[str] = Field(default=None, max_length=10, description="Bill sequence prefix (2-10 uppercase alphanumeric, e.g. BILL)")
    padding_length: int = Field(default=6, ge=4, le=10, description="Serial sequence padding digits (4 to 10, default 6)")
    primary_color: str | None = Field(default=None, description="Primary brand HEX color code (e.g. #1E3A8A)")
    secondary_color: str | None = Field(default=None, description="Secondary brand HEX color code (e.g. #059669)")
    show_gstin: bool = Field(default=True, description="Whether to display GSTIN on printed documents")
    show_qr: bool = Field(default=True, description="Whether to display UPI payment QR code on printed documents")
    show_signature: bool = Field(default=False, description="Whether to include signature box on invoices")
    show_payment_details: bool = Field(default=True, description="Whether to display payment breakdown table")
    logo_path: str | None = Field(default=None, description="Relative URL path to uploaded logo image")

    # Storefront & Online Website Configuration (Unified)
    is_online: Optional[bool] = Field(default=None, description="Whether the online store is open/active for customers")
    tagline: Optional[str] = Field(default=None, description="Store tagline or marketing motto")
    banner_url: Optional[str] = Field(default=None, description="Relative URL to online store hero banner image")
    favicon_url: Optional[str] = Field(default=None, description="Relative URL to browser tab favicon")
    theme_name: Optional[str] = Field(default=None, description="Storefront visual theme preset name")
    custom_domain: Optional[str] = Field(default=None, description="Custom domain e.g. shop.mydomain.com")
    url_slug: Optional[str] = Field(default=None, description="URL path slug")
    meta_title: Optional[str] = Field(default=None, description="SEO meta title for search engines")
    meta_description: Optional[str] = Field(default=None, description="SEO meta description")
    keywords: Optional[str] = Field(default=None, description="Comma-separated SEO keywords")
    google_analytics_id: Optional[str] = Field(default=None, description="Google Analytics 4 Measurement ID")
    about_us: Optional[str] = Field(default=None, description="About Us page text")
    contact_us: Optional[str] = Field(default=None, description="Contact Us page text")
    privacy_policy: Optional[str] = Field(default=None, description="Privacy Policy text")
    return_policy: Optional[str] = Field(default=None, description="Return and refund policy text")
    whatsapp_number: Optional[str] = Field(default=None, description="WhatsApp contact number")
    instagram_url: Optional[str] = Field(default=None, description="Instagram handle or URL")
    facebook_url: Optional[str] = Field(default=None, description="Facebook page or URL")
    twitter_url: Optional[str] = Field(default=None, description="Twitter / X profile URL")
    enable_product_reviews: Optional[bool] = Field(default=None, description="Allow customer product reviews")
    show_out_of_stock: Optional[bool] = Field(default=None, description="Show out-of-stock items in catalog")
    guest_checkout: Optional[bool] = Field(default=None, description="Allow order placement without registering")
    wishlist_enabled: Optional[bool] = Field(default=None, description="Enable customer wishlist")
    auto_sync_inventory: Optional[bool] = Field(default=None, description="Auto sync inventory with POS sales")
    enable_coupons: Optional[bool] = Field(default=None, description="Enable promo coupon discounts")
    gst_invoice_enabled: Optional[bool] = Field(default=None, description="Generate GST invoice for online orders")

    @field_validator("email")
    @classmethod
    def validate_branding_email(cls, v: str | None) -> str | None:
        if not v or not v.strip():
            return None
        return validate_email_address(v, field_name="Branding email", required=False)

    @field_validator("phone", mode="before")
    @classmethod
    def validate_branding_phone(cls, v: str | None) -> str | None:
        if v is None or not str(v).strip():
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


class DocumentSettingDeleteResponse(BaseModel):
    message: str = Field(..., description="Status message")


class DocumentLogoUploadResponse(BaseModel):
    message: str = Field(..., description="Status message")
    logo_url: str = Field(..., description="Uploaded logo URL")
    setting: DocumentSettingResponse


class DocumentLogoDeleteResponse(BaseModel):
    message: str = Field(..., description="Status message")
    setting: DocumentSettingResponse
