from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.ecommerce import (
    EcommerceDashboardResponse,
    EcommerceKPIsResponse,
    OrderStatusBreakdownResponse,
    RecentOnlineOrdersResponse,
    RevenueComparisonResponse,
    TopSellingProductsResponse,
)
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
    StorefrontStatusToggleRequest,
    StorefrontUploadResponse,
)
from app.services.ecommerce_service import EcommerceService
from app.services.storefront_service import StorefrontService

router = APIRouter(prefix="/ecommerce", tags=["E-Commerce"])


def require_ecommerce_access(user: User = Depends(get_current_user)) -> User:
    perms = user.role.permissions if user.role else []
    if "*" in perms or "ecommerce:read" in perms or "dashboard:read" in perms:
        return user

    if user.role and user.role.name in ["admin", "owner"]:
        return user

    raise ForbiddenException("Missing permission: ecommerce:read")


def require_storefront_write(user: User = Depends(get_current_user)) -> User:
    perms = user.role.permissions if user.role else []
    if "*" in perms or "ecommerce:write" in perms or "stores:write" in perms:
        return user

    if user.role and user.role.name in ["admin", "owner"]:
        return user

    raise ForbiddenException("Missing permission: ecommerce:write")


def _resolve_effective_store_id(
    user: User,
    store_id: Optional[int],
) -> Optional[int]:
    if user.store_id is not None:
        if store_id is not None and store_id != user.store_id:
            raise ForbiddenException(
                "Store staff are not authorized to access other stores' dashboard data"
            )
        return user.store_id
    return store_id


# ============================================================
# 1. E-COMMERCE DASHBOARD & ANALYTICS APIs
# ============================================================

@router.get(
    "/dashboard",
    response_model=EcommerceDashboardResponse,
    summary="Get full e-commerce dashboard overview (KPIs, Charts, Orders, Top Products)",
)
def get_ecommerce_dashboard(
    period: str = Query(
        default="this_year",
        description="Time period: today, this_week, this_month, last_month, this_year, or all_time",
        pattern="^(today|this_week|this_month|last_month|this_year|all_time)$",
    ),
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Optional store ID filter for outlet-specific analytics",
    ),
    user: User = Depends(require_ecommerce_access),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return EcommerceService(db).get_full_dashboard(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        period=period,
    )


@router.get(
    "/dashboard/kpis",
    response_model=EcommerceKPIsResponse,
    summary="Get 8 e-commerce KPI metrics cards",
)
def get_ecommerce_kpis(
    period: str = Query(
        default="this_year",
        description="KPI period: today, this_week, this_month, last_month, this_year, or all_time",
        pattern="^(today|this_week|this_month|last_month|this_year|all_time)$",
    ),
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Optional store ID filter for outlet-specific analytics",
    ),
    user: User = Depends(require_ecommerce_access),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return EcommerceService(db).get_kpis(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        period=period,
    )


@router.get(
    "/dashboard/revenue-comparison",
    response_model=RevenueComparisonResponse,
    summary="Get online vs offline POS revenue comparison timeseries chart",
)
def get_revenue_comparison(
    period: str = Query(
        default="this_year",
        description="Period: today, this_week, this_month, last_month, this_year, or all_time",
        pattern="^(today|this_week|this_month|last_month|this_year|all_time)$",
    ),
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Optional store ID filter",
    ),
    user: User = Depends(require_ecommerce_access),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return EcommerceService(db).get_revenue_comparison(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        period=period,
    )


@router.get(
    "/dashboard/order-status-breakdown",
    response_model=OrderStatusBreakdownResponse,
    summary="Get online order status breakdown donut chart data",
)
def get_order_status_breakdown(
    period: str = Query(
        default="this_year",
        description="Period: today, this_week, this_month, last_month, this_year, or all_time",
        pattern="^(today|this_week|this_month|last_month|this_year|all_time)$",
    ),
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Optional store ID filter",
    ),
    user: User = Depends(require_ecommerce_access),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return EcommerceService(db).get_order_status_breakdown(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        period=period,
    )


@router.get(
    "/dashboard/recent-orders",
    response_model=RecentOnlineOrdersResponse,
    summary="Get recent online orders for dashboard table",
)
def get_recent_orders(
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Number of recent orders to fetch",
    ),
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Optional store ID filter",
    ),
    user: User = Depends(require_ecommerce_access),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return EcommerceService(db).get_recent_online_orders(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        limit=limit,
    )


@router.get(
    "/dashboard/top-products",
    response_model=TopSellingProductsResponse,
    summary="Get top selling products online with visual progress rankings",
)
def get_top_products(
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Number of top products to fetch",
    ),
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Optional store ID filter",
    ),
    user: User = Depends(require_ecommerce_access),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return EcommerceService(db).get_top_selling_products(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        limit=limit,
    )


# ============================================================
# 2. STORE MANAGEMENT & STOREFRONT SETTINGS APIs (/ecommerce/store)
# ============================================================

# Master Settings Endpoint
@router.get(
    "/storefront/settings",
    response_model=StorefrontSettingResponse,
    summary="Get All Store Management Settings (Branding, SEO, Pages, Contact, Advanced)",
)
def get_storefront_settings(
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Optional store ID filter",
    ),
    user: User = Depends(require_ecommerce_access),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return StorefrontService(db).get_settings(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
    )


@router.put(
    "/storefront/settings",
    response_model=StorefrontSettingResponse,
    summary="Save Store Management Settings changes (Invoked by Save Changes button)",
)
def update_storefront_settings(
    data: StorefrontSettingUpdate,
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Optional store ID filter",
    ),
    user: User = Depends(require_storefront_write),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return StorefrontService(db).update_settings(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        data=data,
    )


@router.patch(
    "/storefront/toggle-status",
    response_model=StorefrontSettingResponse,
    summary="Toggle Store Online Switch (Store Online)",
)
def toggle_store_online_status(
    data: StorefrontStatusToggleRequest,
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Optional store ID filter",
    ),
    user: User = Depends(require_storefront_write),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return StorefrontService(db).toggle_online_status(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        is_online=data.is_online,
    )


@router.post(
    "/storefront/upload-asset",
    response_model=StorefrontUploadResponse,
    summary="Upload media assets (Store Logo, Store Banner, Favicon)",
)
async def upload_storefront_asset(
    asset_type: str = Form(..., description="Asset type: logo, banner, favicon, or og_image"),
    file: UploadFile = File(..., description="Media file (PNG, JPG, SVG, ICO, WEBP)"),
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Optional store ID filter",
    ),
    user: User = Depends(require_storefront_write),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    content = await file.read()
    return StorefrontService(db).upload_asset(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        asset_type=asset_type,
        filename=file.filename or "",
        content=content,
    )


# --- Tab 2: SEO & Domain APIs ---
@router.get(
    "/storefront/seo-domain",
    response_model=StorefrontSEODomainResponse,
    summary="Get SEO & Domain Settings Tab data",
)
def get_seo_domain_settings(
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_ecommerce_access),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return StorefrontService(db).get_seo_domain(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
    )


@router.put(
    "/storefront/seo-domain",
    response_model=StorefrontSEODomainResponse,
    summary="Save SEO & Domain Settings Tab data",
)
def update_seo_domain_settings(
    data: StorefrontSEODomainUpdate,
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_storefront_write),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return StorefrontService(db).update_seo_domain(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        data=data,
    )


# --- Tab 3: Store Pages APIs ---
@router.get(
    "/storefront/pages",
    response_model=StorefrontPagesResponse,
    summary="Get Store Pages Tab data (About Us, Contact, Privacy, Terms, Returns)",
)
def get_store_pages(
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_ecommerce_access),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return StorefrontService(db).get_pages(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
    )


@router.put(
    "/storefront/pages",
    response_model=StorefrontPagesResponse,
    summary="Save Store Pages Tab data",
)
def update_store_pages(
    data: StorefrontPagesUpdate,
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_storefront_write),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return StorefrontService(db).update_pages(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        data=data,
    )


# --- Tab 4: Contact & Social APIs ---
@router.get(
    "/storefront/contact-social",
    response_model=StorefrontContactSocialResponse,
    summary="Get Contact & Social Media Links Tab data",
)
def get_contact_social_settings(
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_ecommerce_access),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return StorefrontService(db).get_contact_social(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
    )


@router.put(
    "/storefront/contact-social",
    response_model=StorefrontContactSocialResponse,
    summary="Save Contact & Social Media Links Tab data",
)
def update_contact_social_settings(
    data: StorefrontContactSocialUpdate,
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_storefront_write),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return StorefrontService(db).update_contact_social(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        data=data,
    )


# --- Tab 5: Advanced Settings APIs ---
@router.get(
    "/storefront/advanced",
    response_model=StorefrontAdvancedSettingsResponse,
    summary="Get Advanced Feature Switches Tab data (7 Toggles)",
)
def get_advanced_settings(
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_ecommerce_access),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return StorefrontService(db).get_advanced_settings(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
    )


@router.put(
    "/storefront/advanced",
    response_model=StorefrontAdvancedSettingsResponse,
    summary="Save Advanced Feature Switches Tab data",
)
def update_advanced_settings(
    data: StorefrontAdvancedSettingsUpdate,
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_storefront_write),
    db: Session = Depends(get_db),
):
    effective_store_id = _resolve_effective_store_id(user, store_id)
    return StorefrontService(db).update_advanced_settings(
        tenant_id=user.tenant_id,
        store_id=effective_store_id,
        data=data,
    )


# Public Storefront Profile
@router.get(
    "/storefront/public",
    response_model=StorefrontSettingResponse,
    summary="Get public storefront profile (Customer-facing, no authentication)",
)
def get_public_storefront(
    subdomain: Optional[str] = Query(default=None, description="Subdomain slug of store"),
    store_id: Optional[int] = Query(default=None, description="Store ID"),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_public_storefront(
        subdomain=subdomain,
        store_id=store_id,
    )
