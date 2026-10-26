from decimal import Decimal
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    Path,
    Query,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.coupon import (
    ApplicableCouponsResponse,
    ApplyCouponRequest,
    ApplyCouponResponse,
    BulkGenerateCouponsRequest,
    BulkGenerateCouponsResponse,
    CouponCreate,
    CouponRedemptionResponse,
    CouponResponse,
    CouponStatsResponse,
    CouponStatusUpdate,
    CouponUpdate,
    ValidateCouponRequest,
    ValidateCouponResponse,
)
from app.services.coupon_service import CouponService


router = APIRouter(
    prefix="/coupons",
    tags=["Coupons"],
)


@router.get(
    "",
    response_model=list[CouponResponse],
    summary="List all coupons",
)
def list_coupons(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Page size"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by code or description"),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return CouponService(db).list_coupons(
        tenant_id=user.tenant_id,
        page=page,
        page_size=page_size,
        is_active=is_active,
        search=search,
    )


@router.post(
    "",
    response_model=CouponResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new coupon",
)
def create_coupon(
    data: CouponCreate,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return CouponService(db).create_coupon(
        tenant_id=user.tenant_id,
        data=data,
    )


@router.get(
    "/active",
    response_model=list[CouponResponse],
    summary="Get active coupons",
)
def get_active_coupons(
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return CouponService(db).get_active_coupons(
        tenant_id=user.tenant_id
    )


@router.get(
    "/expired",
    response_model=list[CouponResponse],
    summary="Get expired coupons",
)
def get_expired_coupons(
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return CouponService(db).get_expired_coupons(
        tenant_id=user.tenant_id
    )


@router.get(
    "/stats",
    response_model=CouponStatsResponse,
    summary="Get coupon statistics",
)
def get_coupon_stats(
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return CouponService(db).get_coupon_stats(
        tenant_id=user.tenant_id
    )


@router.get(
    "/applicable",
    response_model=ApplicableCouponsResponse,
    summary="Get applicable and locked coupon recommendations for a cart amount",
)
def get_applicable_coupons(
    order_amount: Decimal = Query(..., gt=0, description="Current cart/order amount"),
    customer_id: Optional[int] = Query(None, description="Customer ID"),
    customer_phone: Optional[str] = Query(None, description="Customer phone number"),
    store_id: Optional[int] = Query(None, description="Store ID"),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return CouponService(db).get_applicable_coupons(
        tenant_id=user.tenant_id,
        order_amount=order_amount,
        customer_id=customer_id,
        customer_phone=customer_phone,
        store_id=store_id,
    )


@router.get(
    "/export",
    summary="Export coupons report to Excel, CSV or PDF",
)
def export_coupons(
    format: str = Query("excel", description="Export format: excel, csv or pdf"),
    status: Optional[str] = Query(None, description="Filter status: active, expired, inactive, scheduled"),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    buffer, media_type, filename = CouponService(db).export_coupons(
        tenant_id=user.tenant_id,
        status=status,
        format=format,
    )
    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post(
    "/bulk-generate",
    response_model=BulkGenerateCouponsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk generate unique single-use coupon codes",
)
def bulk_generate_coupons(
    data: BulkGenerateCouponsRequest,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return CouponService(db).bulk_generate(
        tenant_id=user.tenant_id,
        data=data,
    )


@router.post(
    "/validate",
    response_model=ValidateCouponResponse,
    summary="Validate coupon code against order amount and customer",
)
def validate_coupon(
    data: ValidateCouponRequest,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    return CouponService(db).validate_coupon(
        tenant_id=user.tenant_id,
        coupon_code=data.coupon_code,
        order_amount=data.order_amount,
        customer_id=data.customer_id,
        customer_phone=data.customer_phone,
        store_id=data.store_id,
    )


@router.post(
    "/apply",
    response_model=ApplyCouponResponse,
    summary="Apply coupon and calculate discount amount",
)
def apply_coupon(
    data: ApplyCouponRequest,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    return CouponService(db).apply_coupon(
        tenant_id=user.tenant_id,
        coupon_code=data.coupon_code,
        order_amount=data.order_amount,
        customer_id=data.customer_id,
        customer_phone=data.customer_phone,
        store_id=data.store_id,
    )


@router.get(
    "/{coupon_id}/redemptions",
    response_model=list[CouponRedemptionResponse],
    summary="List customer redemptions for a specific coupon",
)
def list_coupon_redemptions(
    coupon_id: int = Path(..., gt=0, description="Coupon ID must be a positive integer"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return CouponService(db).list_redemptions(
        tenant_id=user.tenant_id,
        coupon_id=coupon_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{coupon_id}",
    response_model=CouponResponse,
    summary="Get coupon by ID",
)
def get_coupon(
    coupon_id: int = Path(
        ...,
        gt=0,
        description="Coupon ID must be a positive integer",
    ),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return CouponService(db).get_coupon(
        tenant_id=user.tenant_id,
        coupon_id=coupon_id,
    )


@router.patch(
    "/{coupon_id}/status",
    response_model=CouponResponse,
    summary="Toggle coupon active status",
)
def update_coupon_status(
    data: CouponStatusUpdate,
    coupon_id: int = Path(
        ...,
        gt=0,
        description="Coupon ID must be a positive integer",
    ),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return CouponService(db).update_coupon_status(
        tenant_id=user.tenant_id,
        coupon_id=coupon_id,
        is_active=data.is_active,
    )


@router.patch(
    "/{coupon_id}",
    response_model=CouponResponse,
    summary="Update coupon details",
)
def update_coupon(
    data: CouponUpdate,
    coupon_id: int = Path(
        ...,
        gt=0,
        description="Coupon ID must be a positive integer",
    ),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return CouponService(db).update_coupon(
        tenant_id=user.tenant_id,
        coupon_id=coupon_id,
        data=data,
    )


@router.delete(
    "/{coupon_id}",
    summary="Delete or safely archive a coupon",
)
def delete_coupon(
    coupon_id: int = Path(
        ...,
        gt=0,
        description="Coupon ID must be a positive integer",
    ),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return CouponService(db).delete_coupon(
        tenant_id=user.tenant_id,
        coupon_id=coupon_id,
    )
