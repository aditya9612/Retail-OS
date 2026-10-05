from datetime import datetime
from pydantic import BaseModel, ConfigDict


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
