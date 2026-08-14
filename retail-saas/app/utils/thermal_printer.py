

from decimal import Decimal
from typing import Literal

PrinterType = Literal["epson", "tvs", "generic"]


def _esc_init() -> str:
    return "\x1b\x40"


def _esc_cut() -> str:
    return "\x1d\x56\x00"


def _esc_bold(on: bool) -> str:
    return "\x1b\x45\x01" if on else "\x1b\x45\x00"


def _esc_align(mode: int) -> str:
    return f"\x1b\x61{chr(mode)}"


def _line(text: str, width: int = 32) -> str:
    return text[:width] + "\n"


def generate_thermal_payload(
    invoice_number: str,
    store_name: str,
    items: list[dict],
    subtotal: Decimal,
    discount: Decimal,
    cgst: Decimal,
    sgst: Decimal,
    igst: Decimal,
    grand_total: Decimal,
    payment_modes: list[str] | None = None,
    customer_name: str | None = None,
    customer_mobile: str | None = None,
    gstin: str | None = None,
    printer_type: PrinterType = "generic",
) -> dict:
    width = 42 if printer_type == "tvs" else 32
    lines: list[str] = [_esc_init(), _esc_align(1), _esc_bold(True)]
    lines.append(_line(store_name.upper(), width))
    lines.append(_esc_bold(False))
    if gstin:
        lines.append(_line(f"GSTIN: {gstin}", width))
    lines.append(_line(f"Invoice: {invoice_number}", width))
    if customer_name:
        lines.append(_line(f"Customer: {customer_name}", width))
    if customer_mobile:
        lines.append(_line(f"Mobile: {customer_mobile}", width))
    lines.append(_line("-" * width, width))
    lines.append(_esc_align(0))

    for item in items:
        name = item.get("product_name", "Item")
        qty = item.get("quantity", 1)
        price = item.get("unit_price", 0)
        total = item.get("total_amount", 0)
        lines.append(_line(f"{name}", width))
        lines.append(_line(f"  {qty} x {price} = {total}", width))

    lines.append(_line("-" * width, width))
    lines.append(_line(f"Subtotal: {subtotal}", width))
    if discount > 0:
        lines.append(_line(f"Discount: -{discount}", width))
    if cgst > 0:
        lines.append(_line(f"CGST: {cgst}", width))
    if sgst > 0:
        lines.append(_line(f"SGST: {sgst}", width))
    if igst > 0:
        lines.append(_line(f"IGST: {igst}", width))
    lines.append(_esc_bold(True))
    lines.append(_line(f"TOTAL: {grand_total}", width))
    lines.append(_esc_bold(False))

    if payment_modes:
        lines.append(_line(f"Paid via: {', '.join(payment_modes)}", width))

    lines.append(_esc_align(1))
    lines.append(_line("Thank you!", width))
    lines.append(_esc_cut())

    payload = "".join(lines)
    encoding = "cp437" if printer_type == "epson" else "utf-8"

    return {
        "printer_type": printer_type,
        "encoding": encoding,
        "payload": payload,
        "byte_payload": payload.encode(encoding, errors="replace").hex(),
    }
