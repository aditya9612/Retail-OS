import hashlib
import io
import random
import time

from barcode.codex import Code128
from barcode.writer import ImageWriter


def generate_barcode(sku: str) -> str:
    digest = hashlib.sha256(sku.encode()).hexdigest()
    numeric = "".join(str(int(c, 16) % 10) for c in digest[:12])
    return numeric


def generate_ean13_barcode(tenant_id: int = 1) -> str:
    t_part = f"{tenant_id % 1000:03d}"
    r_part = f"{random.randint(100000, 999999)}"
    base = f"890{t_part}{r_part}"[:12]
    s = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(base))
    check = (10 - (s % 10)) % 10
    return f"{base}{check}"


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