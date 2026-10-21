from typing import Optional
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
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
