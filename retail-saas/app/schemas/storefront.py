from typing import Optional
from pydantic import BaseModel, Field


# ============================================================
# TAB 1: BRANDING
# ============================================================

class StorefrontBrandingSchema(BaseModel):
    store_name: str = Field(default="RetailOS Shop", description="Name of online storefront")
    tagline: Optional[str] = Field(default="Your trusted neighborhood store — now online", description="Tagline / motto")
    logo_url: Optional[str] = Field(default=None, description="URL/path to store logo")
    banner_url: Optional[str] = Field(default=None, description="URL/path to hero banner")
    favicon_url: Optional[str] = Field(default=None, description="URL/path to favicon")
    primary_color: str = Field(default="#4f46e5", description="Primary brand color (hex)")
    accent_color: str = Field(default="#10b981", description="Accent color (hex)")
    theme_name: str = Field(default="modern_light", description="Theme preset name")


# ============================================================
# TAB 2: SEO & DOMAIN
# ============================================================

class StorefrontSEODomainResponse(BaseModel):
    default_store_url: Optional[str] = Field(default="retailos-shop.mystore.in", description="Default subdomain URL")
    custom_domain: Optional[str] = Field(default=None, description="Custom domain like shop.yourdomain.com")
    url_slug: Optional[str] = Field(default="retailos-shop", description="URL path slug")
    meta_title: Optional[str] = Field(default="RetailOS Shop | Quality Products Online", description="SEO meta title")
    meta_description: Optional[str] = Field(
        default="Shop the best products from RetailOS. Fast delivery, easy returns, and amazing deals every day.",
        description="SEO meta description",
    )
    keywords: Optional[str] = Field(
        default="retail, online store, groceries, electronics, fashion",
        description="Comma-separated SEO keywords",
    )
    google_analytics_id: Optional[str] = Field(default="G-XXXXXXXXXX", description="Google Analytics 4 Measurement ID")

    class Config:
        from_attributes = True


class StorefrontSEODomainUpdate(BaseModel):
    custom_domain: Optional[str] = None
    url_slug: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    keywords: Optional[str] = None
    google_analytics_id: Optional[str] = None


# ============================================================
# TAB 3: STORE PAGES
# ============================================================

class StorefrontPagesResponse(BaseModel):
    about_us: Optional[str] = Field(
        default="We are a trusted retail store committed to serving our community with quality products at fair prices.",
        description="About Us content",
    )
    contact_us: Optional[str] = Field(
        default="Reach out at our store or drop us a message. We're always happy to help!",
        description="Contact Us page content",
    )
    privacy_policy: Optional[str] = Field(
        default="Your privacy is important to us. We do not sell or share your personal data with third parties.",
        description="Privacy policy text",
    )
    terms_conditions: Optional[str] = Field(
        default="By using our store, you agree to our terms of service and return policy.",
        description="Terms and conditions text",
    )
    return_policy: Optional[str] = Field(
        default="Returns are accepted within 7 days of delivery for damaged or incorrect items.",
        description="Return & refund policy text",
    )

    class Config:
        from_attributes = True


class StorefrontPagesUpdate(BaseModel):
    about_us: Optional[str] = None
    contact_us: Optional[str] = None
    privacy_policy: Optional[str] = None
    terms_conditions: Optional[str] = None
    return_policy: Optional[str] = None


# ============================================================
# TAB 4: CONTACT & SOCIAL
# ============================================================

class StorefrontContactSocialResponse(BaseModel):
    contact_email: Optional[str] = Field(default="support@retailos-shop.in", description="Support email")
    contact_phone: Optional[str] = Field(default="+91 98765 43210", description="Store phone number")
    whatsapp_number: Optional[str] = Field(default="+91 98765 43210", description="WhatsApp contact number")
    address: Optional[str] = Field(default="123 MG Road, Bangalore, KA 560001", description="Physical store address")
    instagram_url: Optional[str] = Field(default="@retailos_shop", description="Instagram handle or URL")
    facebook_url: Optional[str] = Field(default="facebook.com/retailos", description="Facebook page or URL")
    twitter_url: Optional[str] = Field(default="@retailos", description="Twitter / X handle or URL")

    class Config:
        from_attributes = True


class StorefrontContactSocialUpdate(BaseModel):
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    whatsapp_number: Optional[str] = None
    address: Optional[str] = None
    instagram_url: Optional[str] = None
    facebook_url: Optional[str] = None
    twitter_url: Optional[str] = None


# ============================================================
# TAB 5: ADVANCED SETTINGS (7 Switches)
# ============================================================

class StorefrontAdvancedSettingsResponse(BaseModel):
    enable_product_reviews: bool = Field(default=True, description="Allow customers to leave ratings and reviews")
    show_out_of_stock: bool = Field(default=True, description="Display products with zero stock as Out of Stock")
    guest_checkout: bool = Field(default=False, description="Allow customers to place orders without creating an account")
    wishlist_enabled: bool = Field(default=True, description="Enable customers to save products for later purchase")
    auto_sync_inventory: bool = Field(default=True, description="Automatically update online stock when POS sales occur")
    enable_coupons: bool = Field(default=True, description="Allow discount coupons and promo codes at checkout")
    gst_invoice_enabled: bool = Field(default=True, description="Automatically generate GST invoice for each online order")

    class Config:
        from_attributes = True


class StorefrontAdvancedSettingsUpdate(BaseModel):
    enable_product_reviews: Optional[bool] = None
    show_out_of_stock: Optional[bool] = None
    guest_checkout: Optional[bool] = None
    wishlist_enabled: Optional[bool] = None
    auto_sync_inventory: Optional[bool] = None
    enable_coupons: Optional[bool] = None
    gst_invoice_enabled: Optional[bool] = None


# ============================================================
# MASTER SETTINGS & TOGGLE SCHEMAS
# ============================================================

class StorefrontStatusToggleRequest(BaseModel):
    is_online: bool = Field(description="Set online store availability on or off")


class StorefrontSettingUpdate(BaseModel):
    is_online: Optional[bool] = None

    # Branding
    store_name: Optional[str] = None
    tagline: Optional[str] = None
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    theme_name: Optional[str] = None

    # SEO & Domain
    default_store_url: Optional[str] = None
    custom_domain: Optional[str] = None
    url_slug: Optional[str] = None
    subdomain: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    keywords: Optional[str] = None
    og_image_url: Optional[str] = None
    google_analytics_id: Optional[str] = None

    # Store Pages
    about_us: Optional[str] = None
    contact_us: Optional[str] = None
    privacy_policy: Optional[str] = None
    terms_conditions: Optional[str] = None
    shipping_policy: Optional[str] = None
    return_policy: Optional[str] = None

    # Contact & Social
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    whatsapp_number: Optional[str] = None
    address: Optional[str] = None
    instagram_url: Optional[str] = None
    facebook_url: Optional[str] = None
    twitter_url: Optional[str] = None
    youtube_url: Optional[str] = None

    # Advanced Settings (Switches)
    enable_product_reviews: Optional[bool] = None
    show_out_of_stock: Optional[bool] = None
    guest_checkout: Optional[bool] = None
    wishlist_enabled: Optional[bool] = None
    auto_sync_inventory: Optional[bool] = None
    enable_coupons: Optional[bool] = None
    gst_invoice_enabled: Optional[bool] = None

    facebook_pixel_id: Optional[str] = None
    custom_css: Optional[str] = None
    custom_js: Optional[str] = None
    is_maintenance_mode: Optional[bool] = None


class StorefrontSettingResponse(BaseModel):
    id: Optional[int] = None
    tenant_id: int
    store_id: Optional[int] = None
    is_online: bool = True

    # Branding
    store_name: str = "RetailOS Shop"
    tagline: Optional[str] = "Your trusted neighborhood store — now online"
    logo_url: Optional[str] = None
    banner_url: Optional[str] = None
    favicon_url: Optional[str] = None
    primary_color: str = "#4f46e5"
    accent_color: str = "#10b981"
    theme_name: str = "modern_light"

    # SEO & Domain
    default_store_url: Optional[str] = "retailos-shop.mystore.in"
    custom_domain: Optional[str] = None
    url_slug: Optional[str] = "retailos-shop"
    subdomain: Optional[str] = None
    meta_title: Optional[str] = "RetailOS Shop | Quality Products Online"
    meta_description: Optional[str] = "Shop the best products from RetailOS. Fast delivery, easy returns, and amazing deals every day."
    keywords: Optional[str] = "retail, online store, groceries, electronics, fashion"
    meta_keywords: Optional[str] = "retail, online store, groceries, electronics, fashion"
    og_image_url: Optional[str] = None
    google_analytics_id: Optional[str] = "G-XXXXXXXXXX"

    # Store Pages
    about_us: Optional[str] = "We are a trusted retail store committed to serving our community with quality products at fair prices."
    contact_us: Optional[str] = "Reach out at our store or drop us a message. We're always happy to help!"
    privacy_policy: Optional[str] = "Your privacy is important to us. We do not sell or share your personal data with third parties."
    terms_conditions: Optional[str] = "By using our store, you agree to our terms of service and return policy."
    shipping_policy: Optional[str] = None
    return_policy: Optional[str] = "Returns are accepted within 7 days of delivery for damaged or incorrect items."

    # Contact & Social
    contact_email: Optional[str] = "support@retailos-shop.in"
    contact_phone: Optional[str] = "+91 98765 43210"
    whatsapp_number: Optional[str] = "+91 98765 43210"
    address: Optional[str] = "123 MG Road, Bangalore, KA 560001"
    instagram_url: Optional[str] = "@retailos_shop"
    facebook_url: Optional[str] = "facebook.com/retailos"
    twitter_url: Optional[str] = "@retailos"
    youtube_url: Optional[str] = None

    # Advanced Settings (Switches)
    enable_product_reviews: bool = True
    show_out_of_stock: bool = True
    guest_checkout: bool = False
    wishlist_enabled: bool = True
    auto_sync_inventory: bool = True
    enable_coupons: bool = True
    gst_invoice_enabled: bool = True

    facebook_pixel_id: Optional[str] = None
    custom_css: Optional[str] = None
    custom_js: Optional[str] = None
    is_maintenance_mode: bool = False

    class Config:
        from_attributes = True


class StorefrontUploadResponse(BaseModel):
    asset_type: str
    url: str
    message: str = "Asset uploaded successfully"
