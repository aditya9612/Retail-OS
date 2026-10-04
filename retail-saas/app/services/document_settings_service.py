from typing import Optional
from sqlalchemy.orm import Session

from app.models.document_setting import DocumentSetting
from app.models.store import Store
from app.models.tenant import Tenant
from app.schemas.document_setting import BrandingContext, DocumentSettingCreate, DocumentSettingUpdate


class DocumentSettingsService:
    def __init__(self, db: Session):
        self.db = db

    def get_setting(self, tenant_id: int, store_id: Optional[int] = None) -> Optional[DocumentSetting]:
        query = self.db.query(DocumentSetting).filter(DocumentSetting.tenant_id == tenant_id)
        if store_id is not None:
            query = query.filter(DocumentSetting.store_id == store_id)
        else:
            query = query.filter(DocumentSetting.store_id.is_(None))
        return query.first()

    def create_or_update_setting(
        self,
        tenant_id: int,
        data: DocumentSettingCreate | DocumentSettingUpdate,
        store_id: Optional[int] = None,
    ) -> DocumentSetting:
        setting = self.get_setting(tenant_id, store_id=store_id)
        if not setting:
            setting = DocumentSetting(
                tenant_id=tenant_id,
                store_id=store_id,
            )
            self.db.add(setting)

        payload = data.model_dump(exclude_unset=True) if hasattr(data, "model_dump") else data.dict(exclude_unset=True)
        for key, value in payload.items():
            if hasattr(setting, key):
                setattr(setting, key, value)

        self.db.commit()
        self.db.refresh(setting)
        return setting

    def resolve_branding(self, tenant_id: int, store_id: Optional[int] = None) -> BrandingContext:
        """
        Resolves effective document branding using standard inheritance hierarchy:
        1. Store-level DocumentSetting overrides
        2. Tenant-level DocumentSetting overrides
        3. Store model details
        4. Tenant model details
        5. Default values
        """
        store_setting = self.get_setting(tenant_id, store_id=store_id) if store_id else None
        tenant_setting = self.get_setting(tenant_id, store_id=None)

        store = (
            self.db.query(Store)
            .filter(Store.id == store_id, Store.tenant_id == tenant_id)
            .first()
            if store_id
            else None
        )
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        t_settings = tenant.settings if tenant and isinstance(tenant.settings, dict) else {}

        # Resolve Business Name
        business_name = ""
        if store_setting and store_setting.business_name is not None:
            business_name = store_setting.business_name
        elif tenant_setting and tenant_setting.business_name is not None:
            business_name = tenant_setting.business_name
        elif store and store.name:
            business_name = store.name
        elif tenant and tenant.name:
            business_name = tenant.name

        # Resolve Address
        address = ""
        if store_setting and store_setting.address is not None:
            address = store_setting.address
        elif tenant_setting and tenant_setting.address is not None:
            address = tenant_setting.address
        elif store and store.address:
            addr_parts = [store.address]
            if getattr(store, "city", None):
                addr_parts.append(store.city)
            if getattr(store, "state", None):
                addr_parts.append(store.state)
            if getattr(store, "pincode", None):
                addr_parts.append(store.pincode)
            address = ", ".join(filter(None, addr_parts))
        elif t_settings.get("address"):
            address = str(t_settings.get("address"))

        # Resolve Phone
        phone = ""
        if store_setting and store_setting.phone is not None:
            phone = store_setting.phone
        elif tenant_setting and tenant_setting.phone is not None:
            phone = tenant_setting.phone
        elif store and store.phone:
            phone = store.phone
        elif t_settings.get("phone"):
            phone = str(t_settings.get("phone"))

        # Resolve Email
        email = ""
        if store_setting and store_setting.email is not None:
            email = store_setting.email
        elif tenant_setting and tenant_setting.email is not None:
            email = tenant_setting.email
        elif store and store.email:
            email = store.email
        elif tenant and tenant.email:
            email = tenant.email

        # Resolve Website
        website = ""
        if store_setting and store_setting.website is not None:
            website = store_setting.website
        elif tenant_setting and tenant_setting.website is not None:
            website = tenant_setting.website
        elif t_settings.get("website"):
            website = str(t_settings.get("website"))

        # Resolve GSTIN
        gstin = ""
        if store_setting and store_setting.gstin is not None:
            gstin = store_setting.gstin
        elif tenant_setting and tenant_setting.gstin is not None:
            gstin = tenant_setting.gstin
        elif store and store.gstin:
            gstin = store.gstin
        elif tenant and tenant.gstin:
            gstin = tenant.gstin

        # Resolve Footer Text
        footer_text = ""
        if store_setting and store_setting.footer_text is not None:
            footer_text = store_setting.footer_text
        elif tenant_setting and tenant_setting.footer_text is not None:
            footer_text = tenant_setting.footer_text

        # Resolve Prefixes
        invoice_prefix = "INV"
        if store_setting and store_setting.invoice_prefix is not None:
            invoice_prefix = store_setting.invoice_prefix
        elif tenant_setting and tenant_setting.invoice_prefix is not None:
            invoice_prefix = tenant_setting.invoice_prefix

        bill_prefix = "BILL"
        if store_setting and store_setting.bill_prefix is not None:
            bill_prefix = store_setting.bill_prefix
        elif tenant_setting and tenant_setting.bill_prefix is not None:
            bill_prefix = tenant_setting.bill_prefix

        # Resolve Display Flags
        if store_setting is not None:
            show_gstin = store_setting.show_gstin
            show_qr = store_setting.show_qr
            show_signature = store_setting.show_signature
            show_payment_details = store_setting.show_payment_details
        elif tenant_setting is not None:
            show_gstin = tenant_setting.show_gstin
            show_qr = tenant_setting.show_qr
            show_signature = tenant_setting.show_signature
            show_payment_details = tenant_setting.show_payment_details
        else:
            show_gstin = True
            show_qr = True
            show_signature = False
            show_payment_details = True

        # Resolve Logo
        logo_url = None
        if store_setting and store_setting.logo_path is not None:
            logo_url = store_setting.logo_path
        elif tenant_setting and tenant_setting.logo_path is not None:
            logo_url = tenant_setting.logo_path
        elif store and getattr(store, "logo_url", None):
            logo_url = store.logo_url
        elif t_settings.get("logo_url"):
            logo_url = str(t_settings.get("logo_url"))

        return BrandingContext(
            business_name=business_name,
            address=address,
            phone=phone,
            email=email,
            website=website,
            gstin=gstin,
            footer_text=footer_text,
            invoice_prefix=invoice_prefix,
            bill_prefix=bill_prefix,
            show_gstin=show_gstin,
            show_qr=show_qr,
            show_signature=show_signature,
            show_payment_details=show_payment_details,
            logo_url=logo_url,
        )
