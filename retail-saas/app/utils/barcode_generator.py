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


def generate_thermal_sticker_image(
    barcode_value: str,
    product_name: str = "",
    selling_price: float = 0.0,
    mrp: float = None,
    store_name: str = None,
    sku: str = None,
) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 500, 250
    sticker = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(sticker)

    # 1. Clean border
    draw.rectangle([(2, 2), (width - 3, height - 3)], outline=(60, 60, 60), width=2)

    # Fonts
    try:
        font_store = ImageFont.truetype("arialbd.ttf", 20)
        font_prod = ImageFont.truetype("arial.ttf", 17)
        font_price = ImageFont.truetype("arialbd.ttf", 20)
        font_mrp = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font_store = font_prod = font_price = font_mrp = ImageFont.load_default()

    # 2. Store Name (Centered)
    st_title = (store_name or "RETAIL STORE").strip().upper()
    if len(st_title) > 30:
        st_title = st_title[:27] + "..."
    st_bbox = draw.textbbox((0, 0), st_title, font=font_store)
    st_w = st_bbox[2] - st_bbox[0]
    draw.text(((width - st_w) / 2, 10), st_title, font=font_store, fill=(0, 0, 0))

    # 3. Product Name (Centered)
    p_name = (product_name or "Product").strip()
    if len(p_name) > 34:
        p_name = p_name[:31] + "..."
    pr_bbox = draw.textbbox((0, 0), p_name, font=font_prod)
    pr_w = pr_bbox[2] - pr_bbox[0]
    draw.text(((width - pr_w) / 2, 36), p_name, font=font_prod, fill=(30, 30, 30))

    # 4. Barcode Image with digits
    bc_buf = io.BytesIO()
    bc = Code128(barcode_value, writer=ImageWriter())
    bc.write(
        bc_buf,
        options={
            "write_text": True,
            "module_height": 12.0,
            "module_width": 0.35,
            "quiet_zone": 2.0,
            "font_size": 11,
            "text_distance": 4.0,
        },
    )
    bc_buf.seek(0)
    bc_img = Image.open(bc_buf)

    bc_target_w = 420
    bc_target_h = int(bc_img.height * (bc_target_w / bc_img.width))
    bc_resized = bc_img.resize((bc_target_w, min(bc_target_h, 130)), Image.Resampling.LANCZOS)

    bc_x = int((width - bc_target_w) / 2)
    sticker.paste(bc_resized, (bc_x, 66))

    # 5. Pricing Row
    try:
        sp_float = float(selling_price) if selling_price is not None else 0.0
    except Exception:
        sp_float = 0.0

    try:
        mrp_float = float(mrp) if mrp is not None else 0.0
    except Exception:
        mrp_float = 0.0

    price_str = f"OUR: Rs. {sp_float:.2f}"
    pr_bbox = draw.textbbox((0, 0), price_str, font=font_price)
    pr_w = pr_bbox[2] - pr_bbox[0]
    draw.text((width - pr_w - 24, 210), price_str, font=font_price, fill=(0, 0, 0))

    if mrp_float > 0 and mrp_float > sp_float:
        mrp_str = f"MRP: Rs. {mrp_float:.2f}"
        draw.text((24, 212), mrp_str, font=font_mrp, fill=(110, 110, 110))
        m_bbox = draw.textbbox((24, 212), mrp_str, font=font_mrp)
        mid_y = (m_bbox[1] + m_bbox[3]) / 2
        draw.line([(24, mid_y), (m_bbox[2], mid_y)], fill=(120, 120, 120), width=1)
    elif mrp_float > 0:
        mrp_str = f"MRP: Rs. {mrp_float:.2f}"
        draw.text((24, 212), mrp_str, font=font_mrp, fill=(110, 110, 110))

    out = io.BytesIO()
    sticker.save(out, format="PNG")
    out.seek(0)
    return out.read()