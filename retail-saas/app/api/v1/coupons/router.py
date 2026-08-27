from fastapi import (
    APIRouter,
    Depends,
    Path,
    status,
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User

from app.schemas.coupon import (
    CouponCreate,
    CouponUpdate,
    CouponResponse,
    ApplyCouponRequest,
    ApplyCouponResponse,
    CouponStatsResponse,
    ValidateCouponRequest,
    ValidateCouponResponse,
    CouponStatusUpdate,
)

from app.services.coupon_service import CouponService


router = APIRouter(
    prefix="/coupons",
    tags=["Coupons"],
)


# ============================================================
# LIST ALL COUPONS
# ============================================================

@router.get(
    "",
    response_model=list[CouponResponse],
)
def list_coupons(
    user: User = Depends(
        require_permission("products:read")
    ),
    db: Session = Depends(get_db),
):

    return CouponService(db).list_coupons(
        user.tenant_id
    )


# ============================================================
# CREATE COUPON
# ============================================================

@router.post(
    "",
    response_model=CouponResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_coupon(
    data: CouponCreate,
    user: User = Depends(
        require_permission("products:write")
    ),
    db: Session = Depends(get_db),
):

    return CouponService(db).create_coupon(
        user.tenant_id,
        data,
    )


# ============================================================
# ACTIVE COUPONS
# ============================================================

@router.get(
    "/active",
    response_model=list[CouponResponse],
)
def get_active_coupons(
    user: User = Depends(
        require_permission("products:read")
    ),
    db: Session = Depends(get_db),
):

    return CouponService(db).get_active_coupons(
        tenant_id=user.tenant_id
    )


# ============================================================
# EXPIRED COUPONS
# ============================================================

@router.get(
    "/expired",
    response_model=list[CouponResponse],
)
def get_expired_coupons(
    user: User = Depends(
        require_permission("products:read")
    ),
    db: Session = Depends(get_db),
):

    return CouponService(db).get_expired_coupons(
        tenant_id=user.tenant_id
    )


# ============================================================
# COUPON STATS
# ============================================================

@router.get(
    "/stats",
    response_model=CouponStatsResponse,
)
def get_coupon_stats(
    user: User = Depends(
        require_permission("products:read")
    ),
    db: Session = Depends(get_db),
):

    return CouponService(db).get_coupon_stats(
        tenant_id=user.tenant_id
    )


# ============================================================
# VALIDATE COUPON
#
# IMPORTANT:
# Keep this BEFORE /{coupon_id}
# ============================================================

@router.post(
    "/validate",
    response_model=ValidateCouponResponse,
)
def validate_coupon(
    data: ValidateCouponRequest,
    user: User = Depends(
        require_permission("orders:write")
    ),
    db: Session = Depends(get_db),
):

    return CouponService(db).validate_coupon(
        tenant_id=user.tenant_id,
        coupon_code=data.coupon_code,
        order_amount=data.order_amount,
    )


# ============================================================
# APPLY COUPON
# ============================================================

@router.post(
    "/apply",
    response_model=ApplyCouponResponse,
)
def apply_coupon(
    data: ApplyCouponRequest,
    user: User = Depends(
        require_permission("orders:write")
    ),
    db: Session = Depends(get_db),
):

    return CouponService(db).apply_coupon(
        tenant_id=user.tenant_id,
        coupon_code=data.coupon_code,
        order_amount=data.order_amount,
    )


# ============================================================
# GET SINGLE COUPON
# ============================================================

@router.get(
    "/{coupon_id}",
    response_model=CouponResponse,
)
def get_coupon(
    coupon_id: int = Path(
        ...,
        gt=0,
        description="Coupon ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("products:read")
    ),
    db: Session = Depends(get_db),
):

    return CouponService(db).get_coupon(
        user.tenant_id,
        coupon_id,
    )


# ============================================================
# UPDATE COUPON STATUS
# ============================================================

@router.patch(
    "/{coupon_id}/status",
    response_model=CouponResponse,
)
def update_coupon_status(
    data: CouponStatusUpdate,
    coupon_id: int = Path(
        ...,
        gt=0,
        description="Coupon ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("products:write")
    ),
    db: Session = Depends(get_db),
):

    return CouponService(db).update_coupon_status(
        tenant_id=user.tenant_id,
        coupon_id=coupon_id,
        is_active=data.is_active,
    )


# ============================================================
# UPDATE COUPON
# ============================================================

@router.patch(
    "/{coupon_id}",
    response_model=CouponResponse,
)
def update_coupon(
    data: CouponUpdate,
    coupon_id: int = Path(
        ...,
        gt=0,
        description="Coupon ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("products:write")
    ),
    db: Session = Depends(get_db),
):

    return CouponService(db).update_coupon(
        user.tenant_id,
        coupon_id,
        data,
    )


# ============================================================
# DELETE COUPON
# ============================================================

@router.delete(
    "/{coupon_id}",
)
def delete_coupon(
    coupon_id: int = Path(
        ...,
        gt=0,
        description="Coupon ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("products:write")
    ),
    db: Session = Depends(get_db),
):

    return CouponService(db).delete_coupon(
        user.tenant_id,
        coupon_id,
    )