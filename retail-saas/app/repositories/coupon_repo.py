from datetime import date
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.coupon import Coupon, CouponRedemption


class CouponRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        coupon: Coupon,
    ) -> Coupon:
        self.db.add(coupon)
        self.db.commit()
        self.db.refresh(coupon)
        return coupon

    def bulk_create(
        self,
        coupons: list[Coupon],
    ) -> list[Coupon]:
        self.db.add_all(coupons)
        self.db.commit()
        for c in coupons:
            self.db.refresh(c)
        return coupons

    def get_by_id(
        self,
        coupon_id: int,
        tenant_id: int,
    ) -> Coupon | None:
        return (
            self.db.query(Coupon)
            .filter(
                Coupon.id == coupon_id,
                Coupon.tenant_id == tenant_id,
                Coupon.is_deleted == False,
            )
            .first()
        )

    def get_by_code(
        self,
        code: str,
        tenant_id: int,
    ) -> Coupon | None:
        return (
            self.db.query(Coupon)
            .filter(
                Coupon.code == code,
                Coupon.tenant_id == tenant_id,
                Coupon.is_deleted == False,
            )
            .first()
        )

    def list_coupons(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: Optional[int] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
    ) -> list[Coupon]:
        query = (
            self.db.query(Coupon)
            .filter(
                Coupon.tenant_id == tenant_id,
                Coupon.is_deleted == False,
            )
        )
        if is_active is not None:
            query = query.filter(Coupon.is_active == is_active)
        if search:
            s = f"%{search.strip()}%"
            query = query.filter(or_(Coupon.code.ilike(s), Coupon.description.ilike(s)))

        query = query.order_by(Coupon.created_at.desc())
        if skip:
            query = query.offset(skip)
        if limit:
            query = query.limit(limit)

        return query.all()

    def update(
        self,
        coupon: Coupon,
    ) -> Coupon:
        self.db.commit()
        self.db.refresh(coupon)
        return coupon

    def update_status(
        self,
        coupon: Coupon,
    ) -> Coupon:
        self.db.commit()
        self.db.refresh(coupon)
        return coupon

    def delete(
        self,
        coupon: Coupon,
    ) -> None:
        # If coupon has been used, soft-delete to preserve order audit history
        if coupon.used_count > 0:
            coupon.is_deleted = True
            coupon.is_active = False
            self.db.commit()
        else:
            self.db.delete(coupon)
            self.db.commit()

    def get_active_coupons(
        self,
        tenant_id: int,
    ) -> list[Coupon]:
        today = date.today()
        return (
            self.db.query(Coupon)
            .filter(
                Coupon.tenant_id == tenant_id,
                Coupon.is_deleted == False,
                Coupon.is_active.is_(True),
                Coupon.start_date <= today,
                Coupon.end_date >= today,
            )
            .order_by(
                Coupon.end_date.asc()
            )
            .all()
        )

    def get_expired_coupons(
        self,
        tenant_id: int,
    ) -> list[Coupon]:
        today = date.today()
        return (
            self.db.query(Coupon)
            .filter(
                Coupon.tenant_id == tenant_id,
                Coupon.is_deleted == False,
                Coupon.end_date < today,
            )
            .order_by(
                Coupon.end_date.desc()
            )
            .all()
        )

    def list_all_for_stats(
        self,
        tenant_id: int,
    ) -> list[Coupon]:
        return (
            self.db.query(Coupon)
            .filter(
                Coupon.tenant_id == tenant_id,
                Coupon.is_deleted == False,
            )
            .all()
        )

    # -------------------------------------------------------------
    # Redemptions Repository Methods
    # -------------------------------------------------------------
    def create_redemption(
        self,
        redemption: CouponRedemption,
    ) -> CouponRedemption:
        self.db.add(redemption)
        self.db.commit()
        self.db.refresh(redemption)
        return redemption

    def list_redemptions(
        self,
        tenant_id: int,
        coupon_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[CouponRedemption]:
        query = (
            self.db.query(CouponRedemption)
            .filter(CouponRedemption.tenant_id == tenant_id)
        )
        if coupon_id is not None:
            query = query.filter(CouponRedemption.coupon_id == coupon_id)
        return query.order_by(CouponRedemption.redeemed_at.desc()).offset(skip).limit(limit).all()

    def count_customer_redemptions(
        self,
        tenant_id: int,
        coupon_id: int,
        customer_id: Optional[int] = None,
        customer_phone: Optional[str] = None,
    ) -> int:
        query = self.db.query(CouponRedemption).filter(
            CouponRedemption.tenant_id == tenant_id,
            CouponRedemption.coupon_id == coupon_id,
        )
        conditions = []
        if customer_id is not None:
            conditions.append(CouponRedemption.customer_id == customer_id)
        if customer_phone:
            conditions.append(CouponRedemption.customer_phone == customer_phone)

        if not conditions:
            return 0

        query = query.filter(or_(*conditions))
        return query.count()

    def get_for_export(
        self,
        tenant_id: int,
        status: Optional[str] = None,
    ) -> list[Coupon]:
        today = date.today()
        query = self.db.query(Coupon).filter(
            Coupon.tenant_id == tenant_id,
            Coupon.is_deleted == False,
        )
        if status == "active":
            query = query.filter(Coupon.is_active == True, Coupon.start_date <= today, Coupon.end_date >= today)
        elif status == "expired":
            query = query.filter(Coupon.end_date < today)
        elif status == "inactive":
            query = query.filter(Coupon.is_active == False)
        elif status == "scheduled":
            query = query.filter(Coupon.start_date > today)

        return query.order_by(Coupon.created_at.desc()).all()
