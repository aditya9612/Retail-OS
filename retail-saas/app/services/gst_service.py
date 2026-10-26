from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.gst_rate import GstRate
from app.schemas.gst_rate import (
    GstBulkImportItem,
    GstRateCreate,
    GstRateResponse,
    GstRateUpdate,
)


SupplyType = Literal["intra_state", "inter_state"]

MONEY = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")

DEFAULT_INDIAN_GST_RATES = [
    {"hsn_code": "0401", "gst_rate": Decimal("0.00"), "description": "Fresh milk and basic dairy products", "code_type": "HSN"},
    {"hsn_code": "1006", "gst_rate": Decimal("5.00"), "description": "Rice, wheat and basic foodgrains", "code_type": "HSN"},
    {"hsn_code": "1905", "gst_rate": Decimal("18.00"), "description": "Bread, pastries, biscuits and baked goods", "code_type": "HSN"},
    {"hsn_code": "2202", "gst_rate": Decimal("28.00"), "description": "Aerated and sweetened waters/beverages", "code_type": "HSN"},
    {"hsn_code": "6109", "gst_rate": Decimal("12.00"), "description": "T-shirts, singlets and other knitted apparel", "code_type": "HSN"},
    {"hsn_code": "6403", "gst_rate": Decimal("12.00"), "description": "Footwear with outer soles of rubber or leather", "code_type": "HSN"},
    {"hsn_code": "7113", "gst_rate": Decimal("3.00"), "description": "Articles of jewellery and parts thereof of precious metal", "code_type": "HSN"},
    {"hsn_code": "7102", "gst_rate": Decimal("0.25"), "description": "Diamonds, whether or not worked, but not mounted", "code_type": "HSN"},
    {"hsn_code": "8471", "gst_rate": Decimal("18.00"), "description": "Automatic data processing machines, laptops, computers", "code_type": "HSN"},
    {"hsn_code": "8517", "gst_rate": Decimal("18.00"), "description": "Smartphones, telephone sets and transmission devices", "code_type": "HSN"},
    {"hsn_code": "9983", "gst_rate": Decimal("18.00"), "description": "Other professional, technical and business services", "code_type": "SAC"},
    {"hsn_code": "9963", "gst_rate": Decimal("5.00"), "description": "Restaurant, food and catering services", "code_type": "SAC"},
]


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
            description=data.description,
            code_type=data.code_type,
            gst_rate=gst_rate,
            cgst=cgst,
            sgst=sgst,
            igst=igst,
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
        supply_type: SupplyType | None = None,
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

        resp = GstRateResponse.model_validate(rate)
        if supply_type == "intra_state":
            return resp.model_copy(
                update={"igst": Decimal("0.00"), "supply_type": supply_type}
            )
        elif supply_type == "inter_state":
            return resp.model_copy(
                update={
                    "cgst": Decimal("0.00"),
                    "sgst": Decimal("0.00"),
                    "supply_type": supply_type,
                }
            )
        return resp

    def get_rate_by_hsn(
        self,
        tenant_id: int,
        hsn_code: str,
        supply_type: SupplyType | None = None,
    ) -> GstRateResponse:
        rate = (
            self.db.query(GstRate)
            .filter(
                GstRate.tenant_id == tenant_id,
                GstRate.hsn_code == hsn_code.strip(),
            )
            .first()
        )

        if not rate:
            raise NotFoundException(f"GST rate for HSN code '{hsn_code}' not found")

        resp = GstRateResponse.model_validate(rate)
        if supply_type == "intra_state":
            return resp.model_copy(
                update={"igst": Decimal("0.00"), "supply_type": supply_type}
            )
        elif supply_type == "inter_state":
            return resp.model_copy(
                update={
                    "cgst": Decimal("0.00"),
                    "sgst": Decimal("0.00"),
                    "supply_type": supply_type,
                }
            )
        return resp

    def list_rates(
        self,
        tenant_id: int,
    ) -> list[GstRateResponse]:
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

    def list_rate_views(
        self,
        tenant_id: int,
        supply_type: SupplyType | None = None,
        search: Optional[str] = None,
        hsn_code: Optional[str] = None,
        status: Optional[bool] = None,
        code_type: Optional[str] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> Union[list[GstRateResponse], dict]:
        query = self.db.query(GstRate).filter(GstRate.tenant_id == tenant_id)

        if hsn_code:
            query = query.filter(GstRate.hsn_code == hsn_code.strip())

        if search:
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    GstRate.hsn_code.ilike(term),
                    GstRate.description.ilike(term),
                )
            )

        if status is not None:
            query = query.filter(GstRate.status == status)

        if code_type:
            query = query.filter(GstRate.code_type == code_type.strip().upper())

        query = query.order_by(GstRate.id.desc())

        total = query.count()

        if page is not None and page_size is not None:
            query = query.offset((page - 1) * page_size).limit(page_size)

        rates = query.all()

        views = []
        for rate in rates:
            resp = GstRateResponse.model_validate(rate)
            if supply_type == "intra_state":
                views.append(
                    resp.model_copy(
                        update={"igst": Decimal("0.00"), "supply_type": supply_type}
                    )
                )
            elif supply_type == "inter_state":
                views.append(
                    resp.model_copy(
                        update={
                            "cgst": Decimal("0.00"),
                            "sgst": Decimal("0.00"),
                            "supply_type": supply_type,
                        }
                    )
                )
            else:
                views.append(resp)

        if page is not None and page_size is not None:
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": views,
            }

        return views

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

        if data.description is not None:
            rate.description = data.description

        if data.code_type is not None:
            rate.code_type = data.code_type

        if data.gst_rate is not None:
            gst_rate = _validate_gst_rate(data.gst_rate)
            cgst, sgst, igst = self._split_rate(gst_rate)

            rate.gst_rate = gst_rate
            rate.cgst = cgst
            rate.sgst = sgst
            rate.igst = igst

        if data.status is not None:
            rate.status = data.status

        self.db.commit()
        self.db.refresh(rate)

        return GstRateResponse.model_validate(rate)

    def delete_rate(
        self,
        tenant_id: int,
        rate_id: int,
    ) -> dict:
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

        from app.models.product import Product
        linked_products = (
            self.db.query(Product)
            .filter(
                Product.tenant_id == tenant_id,
                Product.hsn_code == rate.hsn_code,
            )
            .count()
        )
        if linked_products > 0:
            raise ConflictException(
                f"Cannot delete GST rate: {linked_products} product(s) are currently associated with HSN code '{rate.hsn_code}'. Deactivate the rate instead."
            )

        hsn = rate.hsn_code
        self.db.delete(rate)
        self.db.commit()

        return {
            "message": f"GST rate for HSN code '{hsn}' deleted successfully"
        }

    def seed_default_rates(self, tenant_id: int) -> dict:
        existing_rows = (
            self.db.query(GstRate.hsn_code)
            .filter(GstRate.tenant_id == tenant_id)
            .all()
        )
        existing_hsn = {r[0] for r in existing_rows}

        seeded_rates = []
        for item in DEFAULT_INDIAN_GST_RATES:
            if item["hsn_code"] in existing_hsn:
                continue

            cgst, sgst, igst = self._split_rate(item["gst_rate"])
            rate = GstRate(
                tenant_id=tenant_id,
                hsn_code=item["hsn_code"],
                description=item["description"],
                code_type=item["code_type"],
                gst_rate=item["gst_rate"],
                cgst=cgst,
                sgst=sgst,
                igst=igst,
                status=True,
            )
            self.db.add(rate)
            seeded_rates.append(rate)

        if seeded_rates:
            self.db.commit()
            for r in seeded_rates:
                self.db.refresh(r)

        all_rates = self.list_rates(tenant_id)
        return {
            "message": f"Successfully seeded {len(seeded_rates)} standard retail GST rates",
            "seeded_count": len(seeded_rates),
            "existing_count": len(existing_hsn),
            "rates": all_rates,
        }

    def bulk_import_rates(self, tenant_id: int, items: list[GstBulkImportItem]) -> dict:
        created_count = 0
        updated_count = 0
        errors = []

        for item in items:
            hsn = item.hsn_code.strip()
            rate_val = _validate_gst_rate(item.gst_rate)
            cgst, sgst, igst = self._split_rate(rate_val)

            existing = (
                self.db.query(GstRate)
                .filter(
                    GstRate.tenant_id == tenant_id,
                    GstRate.hsn_code == hsn,
                )
                .first()
            )

            if existing:
                existing.gst_rate = rate_val
                existing.cgst = cgst
                existing.sgst = sgst
                existing.igst = igst
                if item.description:
                    existing.description = item.description
                if item.code_type:
                    existing.code_type = item.code_type
                existing.status = True
                updated_count += 1
            else:
                new_rate = GstRate(
                    tenant_id=tenant_id,
                    hsn_code=hsn,
                    description=item.description,
                    code_type=item.code_type,
                    gst_rate=rate_val,
                    cgst=cgst,
                    sgst=sgst,
                    igst=igst,
                    status=True,
                )
                self.db.add(new_rate)
                created_count += 1

        self.db.commit()
        all_rates = self.list_rates(tenant_id)

        return {
            "message": f"Bulk import complete: {created_count} created, {updated_count} updated",
            "created_count": created_count,
            "updated_count": updated_count,
            "errors": errors,
            "rates": all_rates,
        }
