from datetime import date
from decimal import Decimal

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

    def __init__(self, db):

        self.db = db
        self.repo = CouponRepository(db)

    def create_coupon(
        self,
        tenant_id: int,
        data: CouponCreate,
    ) -> Coupon:

        code = data.code.strip().upper()

        existing_coupon = self.repo.get_by_code(
            code,
            tenant_id,
        )

        if existing_coupon:
            raise ConflictException(
                "Coupon code already exists"
            )

        coupon = Coupon(
            tenant_id=tenant_id,
            code=code,
            description=data.description.strip(),
            discount_type=data.discount_type,
            discount_value=data.discount_value,
            minimum_order_amount=data.minimum_order_amount,
            maximum_discount=data.maximum_discount,
            usage_limit=data.usage_limit,
            used_count=0,
            start_date=data.start_date,
            end_date=data.end_date,
            is_active=True,
        )

        return self.repo.create(coupon)

    def list_coupons(
        self,
        tenant_id: int,
    ) -> list[Coupon]:

        coupons = self.repo.list_coupons(
            tenant_id
        )

        if not coupons:
            raise NotFoundException(
                "No coupons found"
            )

        return coupons

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
            raise NotFoundException(
                "Coupon not found"
            )

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

        if not update_data:
            raise AppException(
                "At least one field is required for update"
            )

    
        final_start_date = update_data.get(
            "start_date",
            coupon.start_date,
        )

        final_end_date = update_data.get(
            "end_date",
            coupon.end_date,
        )

        final_discount_type = update_data.get(
            "discount_type",
            coupon.discount_type,
        )

        final_discount_value = update_data.get(
            "discount_value",
            coupon.discount_value,
        )

        final_usage_limit = update_data.get(
            "usage_limit",
            coupon.usage_limit,
        )

        if final_start_date < date.today():
            raise AppException(
               "Start date cannot be in the past"
            )

        if final_end_date < final_start_date:
            raise AppException(
                "End date must be on or after start date"
            )

        if final_discount_type not in (
            "percentage",
            "fixed",
        ):
            raise AppException(
               "discount_type must be either "
               "'percentage' or 'fixed'"
            )

        if (
            final_discount_type == "percentage"
            and final_discount_value > Decimal("100")
        ):
            raise AppException(
                "Percentage discount cannot be greater than 100"
            )

        if final_usage_limit < coupon.used_count:
            raise AppException(
                f"Usage limit cannot be less than used count "
                f"({coupon.used_count})"
            )

        final_maximum_discount = update_data.get(
           "maximum_discount",
            coupon.maximum_discount,
        )

        if (
            final_maximum_discount is not None
            and final_discount_type == "percentage"
            and final_maximum_discount <= 0
        ):
            raise AppException(
                 "Maximum discount must be greater than 0"
            )

        for key, value in update_data.items():

            if key == "description":
                value = value.strip()

            if key == "code":
                value = value.strip().upper()

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

        coupon = self.get_coupon(
            tenant_id,
            coupon_id,
        )

        self.repo.delete(coupon)

        return {
            "message": "Coupon deleted successfully",
            "coupon_id": coupon_id,
        }

    def update_coupon_status(
        self,
        tenant_id: int,
        coupon_id: int,
        is_active: bool,
    ):

        coupon = self.get_coupon(
            tenant_id,
            coupon_id,
        )

        if coupon.is_active == is_active:

            raise AppException(
                f"Coupon is already "
                f"{'active' if is_active else 'inactive'}"
            )

        coupon.is_active = is_active

        return self.repo.update_status(coupon)

    def get_valid_coupon(
        self,
        tenant_id: int,
        coupon_code: str,
        order_amount: Decimal,
    ) -> Coupon:

        code = coupon_code.strip().upper()

        coupon = self.repo.get_by_code(
            code,
            tenant_id,
        )

        if not coupon:
            raise NotFoundException(
                "Coupon not found"
            )

        today = date.today()

        if not coupon.is_active:
            raise AppException(
                "Coupon is inactive"
            )

        if today < coupon.start_date:
            raise AppException(
                "Coupon is not started yet"
            )

        if today > coupon.end_date:
            raise AppException(
                "Coupon expired"
            )

        if order_amount < coupon.minimum_order_amount:

            raise AppException(
                f"Minimum order amount is "
                f"{coupon.minimum_order_amount}"
            )

        if coupon.used_count >= coupon.usage_limit:

            raise AppException(
                "Coupon usage limit exceeded"
            )

        return coupon

    def validate_coupon(
        self,
        tenant_id: int,
        coupon_code: str,
        order_amount: Decimal,
    ):

        self.get_valid_coupon(
            tenant_id=tenant_id,
            coupon_code=coupon_code,
            order_amount=order_amount,
        )

        return {
            "valid": True,
            "message": "Coupon is valid",
        }

    def apply_coupon(
        self,
        tenant_id: int,
        coupon_code: str,
        order_amount: Decimal,
    ):

        coupon = self.get_valid_coupon(
            tenant_id=tenant_id,
            coupon_code=coupon_code,
            order_amount=order_amount,
        )

        if coupon.discount_type == "fixed":

            discount = coupon.discount_value

        else:

            discount = (
                order_amount
                * coupon.discount_value
                / Decimal("100")
            )

        if (
            coupon.maximum_discount is not None
            and discount > coupon.maximum_discount
        ):
            discount = coupon.maximum_discount

        discount = min(
            discount,
            order_amount,
        )
        
        final_amount = (
            order_amount - discount
        )

        return {
            "coupon_code": coupon.code,
            "original_amount": order_amount,
            "discount_amount": discount,
            "final_amount": final_amount,
            "message": "Coupon applied successfully",
        }

    def get_active_coupons(
        self,
        tenant_id: int,
    ):

        coupons = self.repo.get_active_coupons(
            tenant_id
        )

        if not coupons:

            raise NotFoundException(
                "No active coupons found"
            )

        return coupons

    def get_expired_coupons(
        self,
        tenant_id: int,
    ):

        coupons = self.repo.get_expired_coupons(
            tenant_id
        )

        if not coupons:

            raise NotFoundException(
                "No expired coupons found"
            )

        return coupons

    def get_coupon_stats(
        self,
        tenant_id: int,
    ):

        today = date.today()

        coupons = self.repo.list_all_for_stats(
            tenant_id
        )

        total = len(coupons)

        active = sum(
            1
            for coupon in coupons
            if (
                coupon.is_active
                and coupon.start_date <= today
                and coupon.end_date >= today
            )
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

        scheduled = sum(
            1
            for coupon in coupons
            if (
                coupon.is_active
                and coupon.start_date > today
            )
        )

        total_used = sum(
            coupon.used_count
            for coupon in coupons
        )

        return {
            "total_coupons": total,
            "active_coupons": active,
            "expired_coupons": expired,
            "inactive_coupons": inactive,
            "scheduled_coupons": scheduled,
            "total_used": total_used,
        }