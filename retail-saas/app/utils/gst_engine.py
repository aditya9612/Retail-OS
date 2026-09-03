from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.gst_rate import GstRate


MONEY = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


def _quantize(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def resolve_gst_rate(
    db: Session,
    tenant_id: int,
    product,
) -> Decimal:
    rate = None

    if getattr(product, "hsn_code", None):
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
            rate = Decimal(str(rate_row.gst_rate))

    if rate is None:
        rate = Decimal(str(product.gst_rate or ZERO))

    if rate < ZERO or rate > HUNDRED:
        raise ValueError("GST rate must be between 0 and 100")

    return _quantize(rate)


def calculate_line_tax(
    quantity: Decimal,
    unit_price: Decimal,
    discount: Decimal,
    gst_rate: Decimal,
    same_state: bool,
):
    quantity = Decimal(str(quantity))
    unit_price = Decimal(str(unit_price))
    discount = Decimal(str(discount))
    gst_rate = Decimal(str(gst_rate or ZERO))

    if quantity <= ZERO:
        raise ValueError("Quantity must be greater than zero")

    if unit_price <= ZERO:
        raise ValueError("Unit price must be greater than zero")

    if discount < ZERO:
        raise ValueError("Discount cannot be negative")

    gross_amount = _quantize(quantity * unit_price)

    if discount > gross_amount:
        raise ValueError("Discount cannot exceed gross amount")

    if gst_rate < ZERO or gst_rate > HUNDRED:
        raise ValueError("GST rate must be between 0 and 100")

    taxable_amount = _quantize(gross_amount - discount)

    gst_amount = _quantize(
        taxable_amount * gst_rate / HUNDRED
    )

    if same_state:
        cgst_amount = _quantize(gst_amount / Decimal("2"))
        sgst_amount = _quantize(gst_amount - cgst_amount)
        igst_amount = ZERO
    else:
        cgst_amount = ZERO
        sgst_amount = ZERO
        igst_amount = gst_amount

    if same_state:
        if cgst_amount + sgst_amount != gst_amount:
            raise ValueError(
                "Total GST amount does not match the sum of CGST and SGST amounts"
            )

        if igst_amount != ZERO:
            raise ValueError(
                "IGST must be zero for intra-state billing"
            )
    else:
        if cgst_amount != ZERO or sgst_amount != ZERO:
            raise ValueError(
                "CGST and SGST must be zero for inter-state billing"
            )

        if igst_amount != gst_amount:
            raise ValueError(
                "Total GST amount does not match IGST amount"
            )

    total_amount = _quantize(
        taxable_amount + gst_amount
    )

    return {
        "taxable_amount": taxable_amount,
        "gst_rate": _quantize(gst_rate),
        "gst_amount": gst_amount,
        "cgst_amount": cgst_amount,
        "sgst_amount": sgst_amount,
        "igst_amount": igst_amount,
        "total_amount": total_amount,
    }


def aggregate_taxes(line_taxes):
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

    if cgst_amount + sgst_amount + igst_amount != gst_amount:
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