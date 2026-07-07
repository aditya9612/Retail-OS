from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.gst_rate import GstRate
from app.schemas.gst_rate import GstRateCreate, GstRateUpdate


class GstService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _split_rate(gst_rate: Decimal) -> tuple[Decimal, Decimal, Decimal]:
        half = (gst_rate / Decimal("2")).quantize(Decimal("0.01"))
        return half, half, gst_rate

    def list_rates(self, tenant_id: int, active_only: bool = True) -> list[GstRate]:
        query = self.db.query(GstRate).filter(GstRate.tenant_id == tenant_id)
        if active_only:
            query = query.filter(GstRate.status.is_(True))
        return query.order_by(GstRate.hsn_code).all()

    def get_rate(self, tenant_id: int, rate_id: int) -> GstRate:
        rate = (
            self.db.query(GstRate)
            .filter(GstRate.id == rate_id, GstRate.tenant_id == tenant_id)
            .first()
        )
        if not rate:
            raise NotFoundException("GST rate not found")
        return rate

    def create_rate(self, tenant_id: int, data: GstRateCreate) -> GstRate:
        existing = (
            self.db.query(GstRate)
            .filter(GstRate.tenant_id == tenant_id, GstRate.hsn_code == data.hsn_code)
            .first()
        )
        if existing:
            raise ConflictException(f"GST rate for HSN {data.hsn_code} already exists")
        cgst, sgst, igst = self._split_rate(data.gst_rate)
        rate = GstRate(
            tenant_id=tenant_id,
            hsn_code=data.hsn_code,
            gst_rate=data.gst_rate,
            cgst=cgst,
            sgst=sgst,
            igst=igst,
            status=True,
        )
        self.db.add(rate)
        self.db.commit()
        self.db.refresh(rate)
        return rate

    def update_rate(self, tenant_id: int, rate_id: int, data: GstRateUpdate) -> GstRate:
        rate = self.get_rate(tenant_id, rate_id)
        if data.gst_rate is not None:
            rate.gst_rate = data.gst_rate
            rate.cgst, rate.sgst, rate.igst = self._split_rate(data.gst_rate)
        if data.status is not None:
            rate.status = data.status
        self.db.commit()
        self.db.refresh(rate)
        return rate
