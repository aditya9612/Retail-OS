from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.gst_rate import GstRate
from app.schemas.gst_rate import GstRateCreate, GstRateResponse, GstRateUpdate


SupplyType = Literal["intra_state", "inter_state"]

MONEY = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


def _money(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _validate_gst_rate(value: Decimal) -> Decimal:
    value = Decimal(str(value))

    if value < ZERO or value > HUNDRED:
        raise ValueError("GST rate must be between 0 and 100")

    return _money(value)


class GstService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _split_rate(gst_rate: Decimal):
        gst_rate = _validate_gst_rate(gst_rate)

        cgst = _money(gst_rate / Decimal("2"))
        sgst = _money(gst_rate - cgst)
        igst = gst_rate

        if cgst + sgst != gst_rate:
            raise ValueError(
                "CGST and SGST must exactly equal the total GST rate"
            )

        return cgst, sgst, igst

    def create_rate(
        self,
        tenant_id: int,
        data: GstRateCreate,
    ) -> GstRateResponse:
        gst_rate = _validate_gst_rate(data.gst_rate)

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
                "GST rate already exists for this HSN code"
            )

        cgst, sgst, igst = self._split_rate(gst_rate)

        rate = GstRate(
            tenant_id=tenant_id,
            hsn_code=data.hsn_code,
            gst_rate=gst_rate,
            cgst_rate=cgst,
            sgst_rate=sgst,
            igst_rate=igst,
            status=True,
        )

        self.db.add(rate)
        self.db.commit()
        self.db.refresh(rate)

        return GstRateResponse.model_validate(rate)

    def get_rate(
        self,
        tenant_id: int,
        rate_id: int,
    ) -> GstRateResponse:
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

        return GstRateResponse.model_validate(rate)

    def list_rates(
        self,
        tenant_id: int,
    ):
        rates = (
            self.db.query(GstRate)
            .filter(GstRate.tenant_id == tenant_id)
            .order_by(GstRate.id.desc())
            .all()
        )

        return [
            GstRateResponse.model_validate(rate)
            for rate in rates
        ]

    def update_rate(
        self,
        tenant_id: int,
        rate_id: int,
        data: GstRateUpdate,
    ) -> GstRateResponse:
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

        if data.hsn_code is not None and data.hsn_code != rate.hsn_code:
            existing = (
                self.db.query(GstRate)
                .filter(
                    GstRate.tenant_id == tenant_id,
                    GstRate.hsn_code == data.hsn_code,
                    GstRate.id != rate_id,
                )
                .first()
            )

            if existing:
                raise ConflictException(
                    "GST rate already exists for this HSN code"
                )

            rate.hsn_code = data.hsn_code

        if data.gst_rate is not None:
            gst_rate = _validate_gst_rate(data.gst_rate)
            cgst, sgst, igst = self._split_rate(gst_rate)

            rate.gst_rate = gst_rate
            rate.cgst_rate = cgst
            rate.sgst_rate = sgst
            rate.igst_rate = igst

        if data.status is not None:
            rate.status = data.status

        self.db.commit()
        self.db.refresh(rate)

        return GstRateResponse.model_validate(rate)

    def delete_rate(
        self,
        tenant_id: int,
        rate_id: int,
    ):
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

        self.db.delete(rate)
        self.db.commit()

        return {
            "message": "GST rate deleted successfully"
        }