from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import (
    ConflictException,
    NotFoundException,
    AppException,
)
from app.models.coupon import Coupon
from app.repositories.coupon_repo import CouponRepository
from app.schemas.coupon import (
    CouponCreate,
    CouponUpdate,
)


class CouponService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = CouponRepository(db)

    def create_coupon(
        self,
        tenant_id: int,
        data: CouponCreate,
    ) -> Coupon:

        existing_coupon = self.repo.get_by_code(
            data.code,
            tenant_id,
        )

        if existing_coupon:
            raise ConflictException("Coupon code already exists")

        if data.start_date > data.end_date:
            raise AppException(
                "Valid From date cannot be greater than Valid Until date"
            )

        coupon = Coupon(
            tenant_id=tenant_id,
            **data.model_dump()
        )

        return self.repo.create(coupon)

    def list_coupons(
        self,
        tenant_id: int,
    ) -> list[Coupon]:

        return self.repo.list_coupons(tenant_id)

    def get_coupon(
        self,
        tenant_id: int,
        coupon_id: int,
    ) -> Coupon:

        coupon = self.repo.get_by_id(
            coupon_id,
            tenant_id,
        )

        if not coupon:
            raise NotFoundException("Coupon not found")

        return coupon

    def update_coupon(
        self,
        tenant_id: int,
        coupon_id: int,
        data: CouponUpdate,
    ) -> Coupon:

        coupon = self.get_coupon(
            tenant_id,
            coupon_id,
        )

        update_data = data.model_dump(
            exclude_unset=True
        )

        if (
            "code" in update_data
            and update_data["code"] != coupon.code
        ):
            existing_coupon = self.repo.get_by_code(
                update_data["code"],
                tenant_id,
            )

            if existing_coupon:
                raise ConflictException(
                    "Coupon code already exists"
                )

        valid_from = update_data.get(
            "start_date",
            coupon.start_date,
        )

        valid_until = update_data.get(
            "end_date",
            coupon.end_date,
        )

        if valid_from > valid_until:
            raise AppException(
                "Valid From date cannot be greater than Valid Until date"
            )

        for key, value in update_data.items():
            setattr(
                coupon,
                key,
                value,
            )

        return self.repo.update(coupon)

    def delete_coupon(
        self,
        tenant_id: int,
        coupon_id: int,
    ):
        coupon = self.repo.get_by_id(coupon_id, tenant_id)
 
        if not coupon:
           raise NotFoundException("Coupon not found")

        self.repo.delete(coupon)

        return {
           "message": "Coupon deleted successfully"
        }
    
    def apply_coupon(
        self,
        tenant_id: int,
        coupon_code: str,
        order_amount: Decimal,
    ):

        validation = self.validate_coupon(
        tenant_id=tenant_id,
        coupon_code=coupon_code,
        order_amount=order_amount,
    )

        if not validation["valid"]:
           raise AppException(validation["message"])

        coupon = self.repo.get_by_code(
        coupon_code,
        tenant_id,
    )

        if coupon.discount_type == "fixed":
           discount = coupon.discount_value

        else:
            discount = (
                order_amount * coupon.discount_value
            ) / Decimal("100")

        if (
            coupon.maximum_discount
            and discount > coupon.maximum_discount
        ):
            discount = coupon.maximum_discount

        final_amount = order_amount - discount

        if final_amount < 0:
           final_amount = Decimal("0.00")

        return {
            "coupon_code": coupon.code,
            "original_amount": order_amount,
            "discount_amount": discount,
            "final_amount": final_amount,
            "message": "Coupon applied successfully",
        }
  
    def activate_coupon(
        self,
        tenant_id: int,
        coupon_id: int,
    ):

        coupon = self.get_coupon(
            tenant_id,
            coupon_id,
        )
        
        if coupon.is_active:
            raise AppException(
                "Coupon is already active"
            )
        
        coupon.is_active = True

        return self.repo.update(coupon)

    def deactivate_coupon(
        self,
        tenant_id: int,
        coupon_id: int,
    ):

        coupon = self.get_coupon(
            tenant_id,
            coupon_id,
        )

        if not coupon.is_active:
            raise AppException(
                "Coupon is already inactive"
            )
        coupon.is_active = False

        return self.repo.update(coupon)

    
    def validate_coupon(
        self,
        tenant_id: int,
        coupon_code: str,
        order_amount: Decimal,
    ):
        coupon = self.repo.get_by_code(
            coupon_code,
            tenant_id,
    )

        if not coupon:
           return {
               "valid": False,
               "message": "Coupon not found",
            }

        today = date.today()

        if not coupon.is_active:
           return {
               "valid": False,
               "message": "Coupon is inactive",
            }

        if today < coupon.start_date:
           return {
               "valid": False,
               "message": "Coupon is not started yet",
            }

        if today > coupon.end_date:
           return {
               "valid": False,
               "message": "Coupon expired",
            }

        if order_amount < coupon.minimum_order_amount:
           return {
               "valid": False,
               "message": f"Minimum order amount is {coupon.minimum_order_amount}",
            }

        if coupon.used_count >= coupon.usage_limit:
           return {
               "valid": False,
               "message": "Coupon usage limit exceeded",
            }

        return {
               "valid": True,
               "message": "Coupon is valid",
        }
        
    def get_active_coupons(
        self,
        tenant_id: int,
    ):
        return self.repo.get_active_coupons(
             tenant_id
        )
        
    def get_expired_coupons(
        self,
        tenant_id: int,
    ):

        return self.repo.get_expired_coupons(
            tenant_id
        )
        
    def get_coupon_stats(
        self,
        tenant_id: int,
):

        today = date.today()

        coupons = self.repo.get_coupon_stats(
            tenant_id
    )

        total = len(coupons)

        active = sum(
            1
            for coupon in coupons
            if coupon.is_active
            and coupon.start_date <= today <= coupon.end_date
        )

        expired = sum(
            1
            for coupon in coupons
            if coupon.end_date < today
        )

        inactive = sum(
             1
             for coupon in coupons
             if not coupon.is_active
        )

        used = sum(
            coupon.used_count
            for coupon in coupons
        )

        return {
            "total_coupons": total,
            "active_coupons": active,
            "expired_coupons": expired,
            "inactive_coupons": inactive,
            "total_used": used,
        }