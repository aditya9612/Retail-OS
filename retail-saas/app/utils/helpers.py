from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session

from app.models.gst_rate import GstRate
from app.models.product import Product
from app.core.redis_client import get_redis


MONEY = Decimal("0.01")
ZERO = Decimal("0.00")


def _quantize(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(
        MONEY,
        rounding=ROUND_HALF_UP,
    )


def cache_delete_pattern(pattern: str) -> int:
    try:
        redis = get_redis()
        keys = list(redis.scan_iter(match=pattern))

        if not keys:
            return 0

        return redis.delete(*keys)
    except Exception:
        return 0


def resolve_gst_rate(
    db: Session,
    tenant_id: int,
    product: Product,
) -> Decimal:
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

        if rate_row and rate_row.gst_rate is not None:
            rate = _quantize(
                Decimal(str(rate_row.gst_rate))
            )

            if rate < ZERO or rate > Decimal("100"):
                raise ValueError(
                    "GST rate must be between 0 and 100"
                )

            return rate

    if product.gst_rate is None:
        return ZERO

    rate = _quantize(
        Decimal(str(product.gst_rate))
    )

    if rate < ZERO or rate > Decimal("100"):
        raise ValueError(
            "GST rate must be between 0 and 100"
        )

    return rate


def calculate_line_tax(
    quantity: Decimal,
    unit_price: Decimal,
    discount: Decimal,
    gst_rate: Decimal,
    same_state: bool,
) -> dict:
    quantity = Decimal(str(quantity))
    unit_price = Decimal(str(unit_price))
    discount = Decimal(str(discount))
    rate = (
        ZERO
        if gst_rate is None
        else Decimal(str(gst_rate))
    )

    if quantity <= 0:
        raise ValueError(
            "Quantity must be greater than zero"
        )

    if unit_price <= 0:
        raise ValueError(
            "Unit price must be greater than zero"
        )

    if discount < ZERO:
        raise ValueError(
            "Discount cannot be negative"
        )

    if rate < ZERO or rate > Decimal("100"):
        raise ValueError(
            "GST rate must be between 0 and 100"
        )

    gross_amount = _quantize(
        quantity * unit_price
    )

    if discount > gross_amount:
        raise ValueError(
            "Discount cannot exceed item amount"
        )

    taxable = _quantize(
        gross_amount - discount
    )

    gst_amount = _quantize(
        taxable * rate / Decimal("100")
    )

    if same_state:
        cgst_amount = _quantize(
            gst_amount / Decimal("2")
        )

        sgst_amount = _quantize(
            gst_amount - cgst_amount
        )

        igst_amount = ZERO

        if _quantize(
            cgst_amount + sgst_amount
        ) != gst_amount:
            raise ValueError(
                "Total GST amount does not match the sum of CGST and SGST amounts"
            )

        if igst_amount != ZERO:
            raise ValueError(
                "IGST must be zero for intra-state transactions"
            )

    else:
        cgst_amount = ZERO
        sgst_amount = ZERO
        igst_amount = gst_amount

        if igst_amount != gst_amount:
            raise ValueError(
                "IGST amount does not match total GST amount"
            )

        if (
            cgst_amount != ZERO
            or sgst_amount != ZERO
        ):
            raise ValueError(
                "CGST and SGST must be zero for inter-state transactions"
            )

    total_amount = _quantize(
        taxable + gst_amount
    )

    if same_state:
        if _quantize(
            cgst_amount + sgst_amount
        ) != gst_amount:
            raise ValueError(
                "GST validation failed: CGST + SGST must equal GST"
            )
    else:
        if igst_amount != gst_amount:
            raise ValueError(
                "GST validation failed: IGST must equal GST"
            )

    return {
        "taxable_amount": taxable,
        "gst_rate": rate,
        "gst_amount": gst_amount,
        "cgst_amount": cgst_amount,
        "sgst_amount": sgst_amount,
        "igst_amount": igst_amount,
        "total_amount": total_amount,
    }


def aggregate_taxes(
    line_taxes: list[dict],
) -> dict:
    subtotal = _quantize(
        sum(
            (
                Decimal(str(t["taxable_amount"]))
                for t in line_taxes
            ),
            ZERO,
        )
    )

    gst_amount = _quantize(
        sum(
            (
                Decimal(str(t["gst_amount"]))
                for t in line_taxes
            ),
            ZERO,
        )
    )

    cgst_amount = _quantize(
        sum(
            (
                Decimal(str(t["cgst_amount"]))
                for t in line_taxes
            ),
            ZERO,
        )
    )

    sgst_amount = _quantize(
        sum(
            (
                Decimal(str(t["sgst_amount"]))
                for t in line_taxes
            ),
            ZERO,
        )
    )

    igst_amount = _quantize(
        sum(
            (
                Decimal(str(t["igst_amount"]))
                for t in line_taxes
            ),
            ZERO,
        )
    )

    grand_total = _quantize(
        sum(
            (
                Decimal(str(t["total_amount"]))
                for t in line_taxes
            ),
            ZERO,
        )
    )

    if _quantize(
        cgst_amount
        + sgst_amount
        + igst_amount
    ) != gst_amount:
        raise ValueError(
            "Total GST amount does not match the sum of CGST, SGST and IGST amounts"
        )

    return {
        "subtotal": subtotal,
        "gst_amount": gst_amount,
        "cgst_amount": cgst_amount,
        "sgst_amount": sgst_amount,
        "igst_amount": igst_amount,
        "grand_total": grand_total,
    }