import hashlib
import io

from barcode.codex import Code128
from barcode.writer import ImageWriter


def generate_barcode(sku: str) -> str:
    digest = hashlib.sha256(sku.encode()).hexdigest()
    numeric = "".join(str(int(c, 16) % 10) for c in digest[:12])
    return numeric


def generate_barcode_image(barcode_value: str, product_name: str = "") -> bytes:
    buffer = io.BytesIO()
    barcode = Code128(barcode_value, writer=ImageWriter())
    barcode.write(
        buffer,
        options={
            "write_text": True,
            "text": f"{product_name}\n{barcode_value}" if product_name else barcode_value,
            "module_height": 15.0,
            "module_width": 0.4,
            "quiet_zone": 6.5,
            "font_size": 10,
        },
    )
    buffer.seek(0)
    return buffer.read()