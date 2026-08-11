from fastapi import APIRouter, Depends
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

@router.get("", response_model=list[CouponResponse])
def list_coupons(
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return CouponService(db).list_coupons(user.tenant_id)


@router.post("", response_model=CouponResponse, status_code=201)
def create_coupon(
    data: CouponCreate,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return CouponService(db).create_coupon(user.tenant_id, data)


@router.get("/active", response_model=list[CouponResponse],)
def get_active_coupons(
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return CouponService(db).get_active_coupons(tenant_id=user.tenant_id, )

    
@router.get("/expired", response_model=list[CouponResponse],)
def get_expired_coupons(
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return CouponService(db).get_expired_coupons(tenant_id=user.tenant_id,)
 
 
@router.get("/stats", response_model=CouponStatsResponse,)
def get_coupon_stats(
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return CouponService(db).get_coupon_stats(tenant_id=user.tenant_id,)
    
                   
@router.get("/{coupon_id}", response_model=CouponResponse)
def get_coupon(
    coupon_id: int,
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return CouponService(db).get_coupon(user.tenant_id, coupon_id)


@router.patch("/{coupon_id}/status", response_model=CouponResponse,)
def update_coupon_status(
    coupon_id: int,
    data: CouponStatusUpdate,
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


@router.patch("/{coupon_id}", response_model=CouponResponse)
def update_coupon(
    coupon_id: int,
    data: CouponUpdate,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return CouponService(db).update_coupon(
        user.tenant_id,
        coupon_id,
        data,
    )


@router.delete("/{coupon_id}")
def delete_coupon(
    coupon_id: int,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return CouponService(db).delete_coupon(
        user.tenant_id,
        coupon_id,
    )
 
 
@router.post("/validate",response_model=ValidateCouponResponse,)
def validate_coupon(
    data: ValidateCouponRequest,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    return CouponService(db).validate_coupon(
        tenant_id=user.tenant_id,
        coupon_code=data.coupon_code,
        order_amount=data.order_amount,
    )   
    
@router.post("/apply", response_model=ApplyCouponResponse,)
def apply_coupon(
    data: ApplyCouponRequest,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    return CouponService(db).apply_coupon(
        tenant_id=user.tenant_id,
        coupon_code=data.coupon_code,
        order_amount=data.order_amount,
    )
    
