from pathlib import Path
from typing import Optional
import uuid
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.repositories.storefront_repo import StorefrontRepository
from app.schemas.storefront import (
    StorefrontAdvancedSettingsResponse,
    StorefrontAdvancedSettingsUpdate,
    StorefrontContactSocialResponse,
    StorefrontContactSocialUpdate,
    StorefrontPagesResponse,
    StorefrontPagesUpdate,
    StorefrontSEODomainResponse,
    StorefrontSEODomainUpdate,
    StorefrontSettingResponse,
    StorefrontSettingUpdate,
    StorefrontUploadResponse,
)

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
UPLOAD_DIR = Path("uploads/storefront")


class StorefrontService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = StorefrontRepository(db)

    # --- Master All-in-One Settings ---
    def get_settings(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> StorefrontSettingResponse:
        setting = self.repo.get_settings(tenant_id, store_id)
        res = StorefrontSettingResponse.model_validate(setting)
        # Ensure keywords is populated from meta_keywords if set
        if setting.meta_keywords:
            res.keywords = setting.meta_keywords
        return res

    def update_settings(
        self,
        tenant_id: int,
        store_id: Optional[int],
        data: StorefrontSettingUpdate,
    ) -> StorefrontSettingResponse:
        setting = self.repo.update_settings(tenant_id, store_id, data)
        res = StorefrontSettingResponse.model_validate(setting)
        if setting.meta_keywords:
            res.keywords = setting.meta_keywords
        return res

    def toggle_online_status(
        self,
        tenant_id: int,
        store_id: Optional[int],
        is_online: bool,
    ) -> StorefrontSettingResponse:
        setting = self.repo.toggle_online_status(tenant_id, store_id, is_online)
        return StorefrontSettingResponse.model_validate(setting)

    # --- Tab 2: SEO & Domain ---
    def get_seo_domain(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> StorefrontSEODomainResponse:
        setting = self.repo.get_settings(tenant_id, store_id)
        return StorefrontSEODomainResponse(
            default_store_url=setting.default_store_url or f"{setting.url_slug or 'retailos-shop'}.mystore.in",
            custom_domain=setting.custom_domain,
            url_slug=setting.url_slug,
            meta_title=setting.meta_title,
            meta_description=setting.meta_description,
            keywords=setting.meta_keywords,
            google_analytics_id=setting.google_analytics_id,
        )

    def update_seo_domain(
        self,
        tenant_id: int,
        store_id: Optional[int],
        data: StorefrontSEODomainUpdate,
    ) -> StorefrontSEODomainResponse:
        update_data = StorefrontSettingUpdate(
            custom_domain=data.custom_domain,
            url_slug=data.url_slug,
            meta_title=data.meta_title,
            meta_description=data.meta_description,
            meta_keywords=data.keywords,
            google_analytics_id=data.google_analytics_id,
        )
        setting = self.repo.update_settings(tenant_id, store_id, update_data)
        return StorefrontSEODomainResponse(
            default_store_url=setting.default_store_url,
            custom_domain=setting.custom_domain,
            url_slug=setting.url_slug,
            meta_title=setting.meta_title,
            meta_description=setting.meta_description,
            keywords=setting.meta_keywords,
            google_analytics_id=setting.google_analytics_id,
        )

    # --- Tab 3: Store Pages ---
    def get_pages(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> StorefrontPagesResponse:
        setting = self.repo.get_settings(tenant_id, store_id)
        return StorefrontPagesResponse.model_validate(setting)

    def update_pages(
        self,
        tenant_id: int,
        store_id: Optional[int],
        data: StorefrontPagesUpdate,
    ) -> StorefrontPagesResponse:
        update_data = StorefrontSettingUpdate(
            about_us=data.about_us,
            contact_us=data.contact_us,
            privacy_policy=data.privacy_policy,
            terms_conditions=data.terms_conditions,
            return_policy=data.return_policy,
        )
        setting = self.repo.update_settings(tenant_id, store_id, update_data)
        return StorefrontPagesResponse.model_validate(setting)

    # --- Tab 4: Contact & Social ---
    def get_contact_social(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> StorefrontContactSocialResponse:
        setting = self.repo.get_settings(tenant_id, store_id)
        return StorefrontContactSocialResponse.model_validate(setting)

    def update_contact_social(
        self,
        tenant_id: int,
        store_id: Optional[int],
        data: StorefrontContactSocialUpdate,
    ) -> StorefrontContactSocialResponse:
        update_data = StorefrontSettingUpdate(
            contact_email=data.contact_email,
            contact_phone=data.contact_phone,
            whatsapp_number=data.whatsapp_number,
            address=data.address,
            instagram_url=data.instagram_url,
            facebook_url=data.facebook_url,
            twitter_url=data.twitter_url,
        )
        setting = self.repo.update_settings(tenant_id, store_id, update_data)
        return StorefrontContactSocialResponse.model_validate(setting)

    # --- Tab 5: Advanced Settings ---
    def get_advanced_settings(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> StorefrontAdvancedSettingsResponse:
        setting = self.repo.get_settings(tenant_id, store_id)
        return StorefrontAdvancedSettingsResponse.model_validate(setting)

    def update_advanced_settings(
        self,
        tenant_id: int,
        store_id: Optional[int],
        data: StorefrontAdvancedSettingsUpdate,
    ) -> StorefrontAdvancedSettingsResponse:
        update_data = StorefrontSettingUpdate(
            enable_product_reviews=data.enable_product_reviews,
            show_out_of_stock=data.show_out_of_stock,
            guest_checkout=data.guest_checkout,
            wishlist_enabled=data.wishlist_enabled,
            auto_sync_inventory=data.auto_sync_inventory,
            enable_coupons=data.enable_coupons,
            gst_invoice_enabled=data.gst_invoice_enabled,
        )
        setting = self.repo.update_settings(tenant_id, store_id, update_data)
        return StorefrontAdvancedSettingsResponse.model_validate(setting)

    # --- Asset Upload ---
    def upload_asset(
        self,
        tenant_id: int,
        store_id: Optional[int],
        asset_type: str,
        filename: str,
        content: bytes,
    ) -> StorefrontUploadResponse:
        clean_type = asset_type.strip().lower()
        if clean_type not in {"logo", "banner", "favicon", "og_image"}:
            raise AppException("Invalid asset_type. Allowed: logo, banner, favicon, og_image")

        if not filename:
            raise AppException("Filename cannot be empty")

        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise AppException(f"Unsupported file format '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

        if len(content) > MAX_FILE_SIZE:
            raise AppException("File size exceeds 5MB limit")

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        safe_filename = f"{clean_type}_{tenant_id}_{uuid.uuid4().hex[:8]}{ext}"
        target_path = UPLOAD_DIR / safe_filename

        with open(target_path, "wb") as f:
            f.write(content)

        file_url = f"/uploads/storefront/{safe_filename}"
        self.repo.update_asset(tenant_id, store_id, clean_type, file_url)

        return StorefrontUploadResponse(
            asset_type=clean_type,
            url=file_url,
            message=f"{clean_type.capitalize()} uploaded and updated successfully",
        )

    # --- Public Storefront Profile ---
    def get_public_storefront(
        self,
        tenant_id: Optional[int] = None,
        subdomain: Optional[str] = None,
        store_id: Optional[int] = None,
    ) -> StorefrontSettingResponse:
        setting = self.repo.get_public_storefront(tenant_id, subdomain, store_id)
        if not setting:
            raise NotFoundException("Storefront not found")
        return StorefrontSettingResponse.model_validate(setting)
