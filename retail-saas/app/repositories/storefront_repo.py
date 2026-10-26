from typing import Optional
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.document_setting import DocumentSetting
from app.models.store import Store
from app.models.storefront_setting import StorefrontSetting
from app.models.tenant import Tenant
from app.schemas.storefront import (
    StorefrontAdvancedSettingsUpdate,
    StorefrontContactSocialUpdate,
    StorefrontPagesUpdate,
    StorefrontSEODomainUpdate,
    StorefrontSettingUpdate,
)


class StorefrontRepository:
    def __init__(self, db: Session):
        self.db = db

    def _validate_store(
        self,
        tenant_id: int,
        store_id: Optional[int],
    ) -> Optional[Store]:
        if store_id is None:
            return None

        store = (
            self.db.query(Store)
            .filter(
                Store.id == store_id,
                Store.tenant_id == tenant_id,
            )
            .first()
        )
        if not store:
            raise NotFoundException("Store not found")
        return store

    def get_settings(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> StorefrontSetting:
        self._validate_store(tenant_id, store_id)

        setting = (
            self.db.query(StorefrontSetting)
            .filter(
                StorefrontSetting.tenant_id == tenant_id,
                StorefrontSetting.store_id == store_id,
            )
            .first()
        )

        if not setting and store_id is not None:
            setting = (
                self.db.query(StorefrontSetting)
                .filter(
                    StorefrontSetting.tenant_id == tenant_id,
                    StorefrontSetting.store_id.is_(None),
                )
                .first()
            )

        if not setting:
            default_name = "RetailOS Shop"
            default_slug = "retailos-shop"
            if store_id is not None:
                store = self.db.query(Store).filter(Store.id == store_id).first()
                if store and store.name:
                    default_name = store.name
                    default_slug = store.name.lower().replace(" ", "-")
            else:
                tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
                if tenant and tenant.name:
                    default_name = tenant.name
                    default_slug = tenant.slug if hasattr(tenant, "slug") else "retailos-shop"

            setting = StorefrontSetting(
                tenant_id=tenant_id,
                store_id=store_id,
                is_online=True,
                store_name=default_name,
                url_slug=default_slug,
                default_store_url=f"{default_slug}.mystore.in",
                tagline="Your trusted neighborhood store — now online",
                primary_color="#4f46e5",
                accent_color="#10b981",
                theme_name="modern_light",
            )
            self.db.add(setting)
            self.db.commit()
            self.db.refresh(setting)

        # Fallback to DocumentSetting if logo or business details are not set in storefront
        doc_setting = (
            self.db.query(DocumentSetting)
            .filter(
                DocumentSetting.tenant_id == tenant_id,
                DocumentSetting.store_id == store_id,
            )
            .first()
        )
        if not doc_setting and store_id is not None:
            doc_setting = (
                self.db.query(DocumentSetting)
                .filter(
                    DocumentSetting.tenant_id == tenant_id,
                    DocumentSetting.store_id.is_(None),
                )
                .first()
            )

        if doc_setting:
            needs_save = False
            if not setting.logo_url and doc_setting.logo_path:
                setting.logo_url = doc_setting.logo_path
                needs_save = True
            if setting.store_name in (None, '', 'RetailOS Shop') and doc_setting.business_name:
                setting.store_name = doc_setting.business_name
                needs_save = True
            if not setting.address and doc_setting.address:
                setting.address = doc_setting.address
                needs_save = True
            if not setting.contact_phone and doc_setting.phone:
                setting.contact_phone = doc_setting.phone
                needs_save = True
            if not setting.contact_email and doc_setting.email:
                setting.contact_email = doc_setting.email
                needs_save = True
            if needs_save:
                self.db.commit()
                self.db.refresh(setting)

        return setting

    def update_settings(
        self,
        tenant_id: int,
        store_id: Optional[int],
        data: StorefrontSettingUpdate,
    ) -> StorefrontSetting:
        self._validate_store(tenant_id, store_id)

        setting = (
            self.db.query(StorefrontSetting)
            .filter(
                StorefrontSetting.tenant_id == tenant_id,
                StorefrontSetting.store_id == store_id,
            )
            .first()
        )

        if not setting:
            setting = self.get_settings(tenant_id, store_id)

        update_dict = data.model_dump(exclude_unset=True)
        # Handle keywords alias
        if "keywords" in update_dict and "meta_keywords" not in update_dict:
            update_dict["meta_keywords"] = update_dict["keywords"]

        for key, val in update_dict.items():
            if hasattr(setting, key) and val is not None:
                setattr(setting, key, val)

        # Auto-sync business name and contact info to DocumentSetting if present
        sync_updates = {}
        if "store_name" in update_dict and update_dict["store_name"]:
            sync_updates["business_name"] = update_dict["store_name"]
        if "address" in update_dict and update_dict["address"]:
            sync_updates["address"] = update_dict["address"]
        if "contact_phone" in update_dict and update_dict["contact_phone"]:
            sync_updates["phone"] = update_dict["contact_phone"]
        if "contact_email" in update_dict and update_dict["contact_email"]:
            sync_updates["email"] = update_dict["contact_email"]

        if sync_updates:
            doc_q = self.db.query(DocumentSetting).filter(DocumentSetting.tenant_id == tenant_id)
            if store_id is not None:
                doc_setting = doc_q.filter(DocumentSetting.store_id == store_id).first()
            else:
                doc_setting = doc_q.filter(DocumentSetting.store_id.is_(None)).first()
            if not doc_setting:
                doc_setting = DocumentSetting(
                    tenant_id=tenant_id,
                    store_id=store_id,
                    **sync_updates,
                )
                self.db.add(doc_setting)
            else:
                for k, v in sync_updates.items():
                    setattr(doc_setting, k, v)

        self.db.commit()
        self.db.refresh(setting)
        return setting

    def toggle_online_status(
        self,
        tenant_id: int,
        store_id: Optional[int],
        is_online: bool,
    ) -> StorefrontSetting:
        setting = self.get_settings(tenant_id, store_id)
        setting.is_online = is_online
        self.db.commit()
        self.db.refresh(setting)
        return setting

    def update_asset(
        self,
        tenant_id: int,
        store_id: Optional[int],
        asset_type: str,
        asset_url: str,
    ) -> StorefrontSetting:
        setting = self.get_settings(tenant_id, store_id)
        if asset_type == "logo":
            setting.logo_url = asset_url
            doc_q = self.db.query(DocumentSetting).filter(DocumentSetting.tenant_id == tenant_id)
            if store_id is not None:
                doc_setting = doc_q.filter(DocumentSetting.store_id == store_id).first()
            else:
                doc_setting = doc_q.filter(DocumentSetting.store_id.is_(None)).first()
            if not doc_setting:
                doc_setting = DocumentSetting(
                    tenant_id=tenant_id,
                    store_id=store_id,
                    logo_path=asset_url,
                )
                self.db.add(doc_setting)
            else:
                doc_setting.logo_path = asset_url
        elif asset_type == "banner":
            setting.banner_url = asset_url
        elif asset_type == "favicon":
            setting.favicon_url = asset_url
        elif asset_type == "og_image":
            setting.og_image_url = asset_url

        self.db.commit()
        self.db.refresh(setting)
        return setting

    def get_public_storefront(
        self,
        tenant_id: Optional[int] = None,
        subdomain: Optional[str] = None,
        store_id: Optional[int] = None,
    ) -> Optional[StorefrontSetting]:
        query = self.db.query(StorefrontSetting)
        if subdomain:
            clean_sub = subdomain.strip().lower()
            query = query.filter(
                (StorefrontSetting.subdomain == clean_sub) |
                (StorefrontSetting.url_slug == clean_sub)
            )
        elif tenant_id is not None:
            query = query.filter(StorefrontSetting.tenant_id == tenant_id)
            if store_id is not None:
                query = query.filter(StorefrontSetting.store_id == store_id)
        return query.first()
