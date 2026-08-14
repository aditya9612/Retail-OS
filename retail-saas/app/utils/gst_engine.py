

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.gst_rate import GstRate
from app.models.product import Product


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def resolve_gst_rate(db: Session, tenant_id: int, product: Product) -> Decimal:
    if product.hsn_code:
        rate_row = (
            db.query(GstRate)
            .filter(
                GstRate.tenant_id == tenant_id,
                GstRate.hsn_code == product.hsn_code,
                GstRate.status.is_(True),
            )
            .first()
        )
        if rate_row:
            return rate_row.gst_rate
    return product.gst_rate


def calculate_line_tax(
    quantity: Decimal,
    unit_price: Decimal,
    discount: Decimal,
    gst_rate: Decimal,
    same_state: bool,
) -> dict:
    taxable = _quantize(quantity * unit_price - discount)
    gst_amount = _quantize(taxable * gst_rate / Decimal("100"))
    if same_state:
        half = _quantize(gst_amount / Decimal("2"))
        return {
            "taxable_amount": taxable,
            "gst_rate": gst_rate,
            "gst_amount": gst_amount,
            "cgst_amount": half,
            "sgst_amount": half,
            "igst_amount": Decimal("0.00"),
            "total_amount": _quantize(taxable + gst_amount),
        }
    return {
        "taxable_amount": taxable,
        "gst_rate": gst_rate,
        "gst_amount": gst_amount,
        "cgst_amount": Decimal("0.00"),
        "sgst_amount": Decimal("0.00"),
        "igst_amount": gst_amount,
        "total_amount": _quantize(taxable + gst_amount),
    }


def aggregate_taxes(line_taxes: list[dict]) -> dict:
    return {
        "subtotal": _quantize(sum((t["taxable_amount"] for t in line_taxes), Decimal("0"))),
        "gst_amount": _quantize(sum((t["gst_amount"] for t in line_taxes), Decimal("0"))),
        "cgst_amount": _quantize(sum((t["cgst_amount"] for t in line_taxes), Decimal("0"))),
        "sgst_amount": _quantize(sum((t["sgst_amount"] for t in line_taxes), Decimal("0"))),
        "igst_amount": _quantize(sum((t["igst_amount"] for t in line_taxes), Decimal("0"))),
        "grand_total": _quantize(sum((t["total_amount"] for t in line_taxes), Decimal("0"))),
    }
