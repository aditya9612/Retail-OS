from datetime import date

from sqlalchemy.orm import Session

from app.models.coupon import Coupon


class CouponRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(self, coupon: Coupon) -> Coupon:
        self.db.add(coupon)
        self.db.commit()
        self.db.refresh(coupon)
        return coupon

    def get_by_id(self, coupon_id: int, tenant_id: int) -> Coupon | None:
        return (
            self.db.query(Coupon)
            .filter(
                Coupon.id == coupon_id,
                Coupon.tenant_id == tenant_id,
            )
            .first()
        )

    def get_by_code(self, code: str, tenant_id: int) -> Coupon | None:
        return (
            self.db.query(Coupon)
            .filter(
                Coupon.code == code,
                Coupon.tenant_id == tenant_id,
            )
            .first()
        )

    def list_coupons(self, tenant_id: int) -> list[Coupon]:
        return (
            self.db.query(Coupon)
            .filter(Coupon.tenant_id == tenant_id)
            .order_by(Coupon.created_at.desc())
            .all()
        )

    def update_status(self, coupon: Coupon) -> Coupon:
        self.db.commit()
        self.db.refresh(coupon)
        return coupon

    def delete(self, coupon: Coupon) -> None:
        self.db.delete(coupon)
        self.db.commit()
        
    def get_active_coupons(
        self,
        tenant_id: int,
    ):

        today = date.today()

        return (
            self.db.query(Coupon)
            .filter(
                Coupon.tenant_id == tenant_id,
                Coupon.is_active == True,
                Coupon.start_date <= today,
                Coupon.end_date >= today,
        )
             .all()
    )
        
    def get_expired_coupons(
        self,
        tenant_id: int,
    ):

        today = date.today()

        return (
            self.db.query(Coupon)
            .filter(
                Coupon.tenant_id == tenant_id,
                Coupon.end_date < today,
            )
            .all()
        ) 
        
    def get_coupon_stats(
        self,
        tenant_id: int,
    ):

        return (
            self.db.query(Coupon)
            .filter(
                Coupon.tenant_id == tenant_id,
            )
            .all()
        )