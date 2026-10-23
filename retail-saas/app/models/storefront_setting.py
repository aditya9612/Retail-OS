from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class StorefrontSetting(Base, TimestampMixin):
    __tablename__ = "storefront_settings"
    __table_args__ = (
        Index("ix_storefront_tenant_store", "tenant_id", "store_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True,
    )
    store_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("stores.id"),
        nullable=True,
        index=True,
    )

    # Online Status
    is_online: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # 1. Branding & Identity
    store_name: Mapped[str] = mapped_column(String(255), default="RetailOS Shop", nullable=False)
    tagline: Mapped[Optional[str]] = mapped_column(
        String(500),
        default="Your trusted neighborhood store — now online",
        nullable=True,
    )
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    banner_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    favicon_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(20), default="#4f46e5", nullable=False)
    accent_color: Mapped[str] = mapped_column(String(20), default="#10b981", nullable=False)
    theme_name: Mapped[str] = mapped_column(String(50), default="modern_light", nullable=False)

    # 2. SEO & Domain Settings
    default_store_url: Mapped[Optional[str]] = mapped_column(
        String(255),
        default="retailos-shop.mystore.in",
        nullable=True,
    )
    custom_domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    url_slug: Mapped[Optional[str]] = mapped_column(String(100), default="retailos-shop", nullable=True)
    subdomain: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    meta_title: Mapped[Optional[str]] = mapped_column(
        String(255),
        default="RetailOS Shop | Quality Products Online",
        nullable=True,
    )
    meta_description: Mapped[Optional[str]] = mapped_column(
        Text,
        default="Shop the best products from RetailOS. Fast delivery, easy returns, and amazing deals every day.",
        nullable=True,
    )
    meta_keywords: Mapped[Optional[str]] = mapped_column(
        String(500),
        default="retail, online store, groceries, electronics, fashion",
        nullable=True,
    )
    og_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    google_analytics_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        default="G-XXXXXXXXXX",
        nullable=True,
    )

    # 3. Store Pages
    about_us: Mapped[Optional[str]] = mapped_column(
        Text,
        default="We are a trusted retail store committed to serving our community with quality products at fair prices.",
        nullable=True,
    )
    contact_us: Mapped[Optional[str]] = mapped_column(
        Text,
        default="Reach out at our store or drop us a message. We're always happy to help!",
        nullable=True,
    )
    privacy_policy: Mapped[Optional[str]] = mapped_column(
        Text,
        default="Your privacy is important to us. We do not sell or share your personal data with third parties.",
        nullable=True,
    )
    terms_conditions: Mapped[Optional[str]] = mapped_column(
        Text,
        default="By using our store, you agree to our terms of service and return policy.",
        nullable=True,
    )
    shipping_policy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    return_policy: Mapped[Optional[str]] = mapped_column(
        Text,
        default="Returns are accepted within 7 days of delivery for damaged or incorrect items.",
        nullable=True,
    )

    # 4. Contact & Social
    contact_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        default="support@retailos-shop.in",
        nullable=True,
    )
    contact_phone: Mapped[Optional[str]] = mapped_column(
        String(50),
        default="+91 98765 43210",
        nullable=True,
    )
    whatsapp_number: Mapped[Optional[str]] = mapped_column(
        String(50),
        default="+91 98765 43210",
        nullable=True,
    )
    address: Mapped[Optional[str]] = mapped_column(
        String(500),
        default="123 MG Road, Bangalore, KA 560001",
        nullable=True,
    )
    instagram_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        default="@retailos_shop",
        nullable=True,
    )
    facebook_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        default="facebook.com/retailos",
        nullable=True,
    )
    twitter_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        default="@retailos",
        nullable=True,
    )
    youtube_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # 5. Advanced Settings (7 exact feature switches from screenshot)
    enable_product_reviews: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    show_out_of_stock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    guest_checkout: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    wishlist_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_sync_inventory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enable_coupons: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    gst_invoice_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    facebook_pixel_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    custom_css: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    custom_js: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    store: Mapped[Optional["Store"]] = relationship("Store")
