from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session

from app.models.gst_rate import GstRate
from app.models.product import Product
from app.core.redis_client import get_redis

get_redis_client = get_redis


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


def amount_to_indian_words(amount: Decimal | float | int | str) -> str:
    """
    Converts a numeric amount into words formatted in Indian currency standard.
    Examples:
        354.00 -> 'Indian Rupees Three Hundred Fifty-Four Only'
        12500.50 -> 'Indian Rupees Twelve Thousand Five Hundred and Fifty Paise Only'
    """
    try:
        amt = Decimal(str(amount)).quantize(Decimal("0.01"))
    except Exception:
        return ""

    if amt == Decimal("0.00"):
        return "Indian Rupees Zero Only"

    is_negative = amt < Decimal("0.00")
    amt = abs(amt)

    rupees = int(amt)
    paise = int(round((amt - Decimal(rupees)) * 100))

    ones = [
        "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
        "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
        "Seventeen", "Eighteen", "Nineteen",
    ]
    tens = [
        "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety",
    ]

    def num_to_words_below_1000(n: int) -> str:
        parts = []
        if n >= 100:
            parts.append(f"{ones[n // 100]} Hundred")
            n %= 100
        if n >= 20:
            t = tens[n // 10]
            rem = ones[n % 10]
            parts.append(f"{t}-{rem}" if rem else t)
        elif n > 0:
            parts.append(ones[n])
        return " ".join(parts)

    def convert_rupees(n: int) -> str:
        if n == 0:
            return ""
        parts = []
        crores = n // 10000000
        if crores:
            parts.append(f"{convert_rupees(crores)} Crore")
            n %= 10000000
        lakhs = n // 100000
        if lakhs:
            parts.append(f"{num_to_words_below_1000(lakhs)} Lakh")
            n %= 100000
        thousands = n // 1000
        if thousands:
            parts.append(f"{num_to_words_below_1000(thousands)} Thousand")
            n %= 1000
        if n > 0:
            parts.append(num_to_words_below_1000(n))
        return " ".join(parts)

    result_parts = []
    if is_negative:
        result_parts.append("Minus")

    rupee_words = convert_rupees(rupees)
    if rupee_words:
        result_parts.append(f"Indian Rupees {rupee_words}")

    if paise > 0:
        paise_words = num_to_words_below_1000(paise)
        if rupee_words:
            result_parts.append(f"and {paise_words} Paise")
        else:
            result_parts.append(f"{paise_words} Paise")

    result_parts.append("Only")
    return " ".join(result_parts)