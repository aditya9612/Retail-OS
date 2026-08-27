from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.gst_rate import GstRate
from app.schemas.gst_rate import GstRateCreate, GstRateResponse, GstRateUpdate

SupplyType = Literal["intra_state", "inter_state"]


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

    def list_rate_views(
        self,
        tenant_id: int,
        supply_type: SupplyType | None = None,
        active_only: bool = True,
    ) -> list[GstRateResponse]:
        views = []

        for rate in self.list_rates(tenant_id, active_only=active_only):
            cgst, sgst, igst = self._split_rate(rate.gst_rate)

            base = {
                "id": rate.id,
                "tenant_id": rate.tenant_id,
                "hsn_code": rate.hsn_code,
                "gst_rate": rate.gst_rate,
                "status": rate.status,
                "created_at": rate.created_at,
            }

            if supply_type == "inter_state":
                views.append(
                    GstRateResponse(
                        **base,
                        cgst=Decimal("0.00"),
                        sgst=Decimal("0.00"),
                        igst=igst,
                        supply_type="inter_state",
                    )
                )
            else:
                views.append(
                    GstRateResponse(
                        **base,
                        cgst=cgst,
                        sgst=sgst,
                        igst=Decimal("0.00"),
                        supply_type="intra_state",
                    )
                )

        return views

    def get_rate(self, tenant_id: int, rate_id: int) -> GstRate:
        rate = (
            self.db.query(GstRate)
            .filter(
                GstRate.id == rate_id,
                GstRate.tenant_id == tenant_id,
            )
            .first()
        )

        if not rate:
            raise NotFoundException("GST rate not found")

        return rate

    def create_rate(self, tenant_id: int, data: GstRateCreate) -> GstRate:
        existing = (
            self.db.query(GstRate)
            .filter(
                GstRate.tenant_id == tenant_id,
                GstRate.hsn_code == data.hsn_code,
            )
            .first()
        )

        if existing:
            raise ConflictException(
                f"GST rate for HSN {data.hsn_code} already exists"
            )

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

    def update_rate(
        self,
        tenant_id: int,
        rate_id: int,
        data: GstRateUpdate,
    ) -> GstRate:
        rate = self.get_rate(tenant_id, rate_id)

        if data.gst_rate is not None:
            rate.gst_rate = data.gst_rate
            cgst, sgst, igst = self._split_rate(data.gst_rate)
            rate.cgst = cgst
            rate.sgst = sgst
            rate.igst = igst

        if data.status is not None:
            rate.status = data.status

        self.db.commit()
        self.db.refresh(rate)

        return rate