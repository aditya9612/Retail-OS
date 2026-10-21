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

def generate_thermal_shipping_label_image(
    carrier_name: str = "Standard Fleet",
    is_cod: bool = False,
    cod_amount: float = 0.0,
    awb_number: str = "",
    barcode_data: str = "",
    recipient_name: str = "Customer",
    address: str = "No address provided",
    phone: str = "N/A",
    order_number: str = "ORD-N/A",
    dispatch_date: str = "",
    delivery_id: int = 0,
    status: str = "PENDING",
) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 400, 600
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 1. Outer label border
    draw.rectangle([(8, 8), (width - 9, height - 9)], outline=(0, 0, 0), width=3)

    try:
        font_lg = ImageFont.truetype("arialbd.ttf", 18)
        font_md = ImageFont.truetype("arialbd.ttf", 14)
        font_sm = ImageFont.truetype("arial.ttf", 12)
        font_xs = ImageFont.truetype("arial.ttf", 10)
    except Exception:
        font_lg = font_md = font_sm = font_xs = ImageFont.load_default()

    # 2. Header: Carrier title & Badge
    c_title = (carrier_name or "STANDARD FLEET").strip().upper()
    if len(c_title) > 22:
        c_title = c_title[:20] + "..."
    draw.text((18, 18), c_title, font=font_lg, fill=(0, 0, 0))

    badge_text = f"COD: Rs.{cod_amount:.2f}" if is_cod else "PREPAID"
    bbox = draw.textbbox((0, 0), badge_text, font=font_md)
    bw = bbox[2] - bbox[0] + 16
    bh = 26
    bx = width - 18 - bw
    if is_cod:
        draw.rectangle([(bx, 15), (bx + bw, 15 + bh)], fill=(0, 0, 0))
        draw.text((bx + 8, 19), badge_text, font=font_md, fill=(255, 255, 255))
    else:
        draw.rectangle([(bx, 15), (bx + bw, 15 + bh)], outline=(0, 0, 0), width=2)
        draw.text((bx + 8, 19), badge_text, font=font_md, fill=(0, 0, 0))

    draw.line([(8, 48), (width - 9, 48)], fill=(0, 0, 0), width=2)

    # 3. Barcode section
    raw_code = (barcode_data or awb_number or "100000000000").strip()
    clean_bc = "".join(c for c in raw_code if c.isalnum() or c in "-_") or "100000000000"
    try:
        bc_buf = io.BytesIO()
        bc = Code128(clean_bc[:24], writer=ImageWriter())
        bc.write(
            bc_buf,
            options={
                "write_text": False,
                "module_height": 12.0,
                "module_width": 0.35,
                "quiet_zone": 1.0,
            },
        )
        bc_buf.seek(0)
        bc_img = Image.open(bc_buf)
        bc_w, bc_h = 320, 50
        bc_resized = bc_img.resize((bc_w, bc_h), Image.Resampling.LANCZOS)
        img.paste(bc_resized, ((width - bc_w) // 2, 58))
    except Exception:
        draw.rectangle([(40, 58), (360, 108)], fill=(240, 240, 240), outline=(0, 0, 0))

    awb_str = awb_number or clean_bc
    awb_bbox = draw.textbbox((0, 0), awb_str, font=font_sm)
    awb_w = awb_bbox[2] - awb_bbox[0]
    draw.text(((width - awb_w) // 2, 114), awb_str, font=font_sm, fill=(0, 0, 0))

    # Divider dashed line
    for x in range(12, width - 12, 10):
        draw.line([(x, 134), (x + 5, 134)], fill=(120, 120, 120), width=1)

    # 4. Address section
    draw.text((18, 142), "SHIP TO / DELIVER TO:", font=font_xs, fill=(80, 80, 80))
    recip = (recipient_name or "Retail Customer").strip()
    if len(recip) > 34:
        recip = recip[:31] + "..."
    draw.text((18, 160), recip, font=font_lg, fill=(0, 0, 0))

    # Multiline address wrap
    addr_lines = []
    words = (address or "No address provided").split()
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        if len(test) > 42:
            addr_lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        addr_lines.append(cur)

    y_addr = 188
    for line in addr_lines[:4]:
        draw.text((18, y_addr), line, font=font_sm, fill=(20, 20, 20))
        y_addr += 18

    p_val = (phone or "N/A").strip()
    draw.text((18, y_addr + 4), f"Contact: {p_val}", font=font_md, fill=(0, 0, 0))

    draw.line([(8, 440), (width - 9, 440)], fill=(0, 0, 0), width=2)

    # 5. Footer Grid
    mid_x = width // 2
    draw.line([(mid_x, 440), (mid_x, 590)], fill=(0, 0, 0), width=1)
    draw.line([(8, 515), (width - 9, 515)], fill=(0, 0, 0), width=1)

    # Top-Left: ORDER #
    draw.text((18, 448), "ORDER #", font=font_xs, fill=(90, 90, 90))
    draw.text((18, 466), (order_number or "ORD-N/A")[:18], font=font_md, fill=(0, 0, 0))

    # Top-Right: DISPATCH DATE
    draw.text((mid_x + 12, 448), "DISPATCH DATE", font=font_xs, fill=(90, 90, 90))
    draw.text((mid_x + 12, 466), (dispatch_date or "N/A")[:18], font=font_sm, fill=(0, 0, 0))

    # Bottom-Left: DELIVERY ID
    draw.text((18, 523), "DELIVERY ID", font=font_xs, fill=(90, 90, 90))
    draw.text((18, 542), f"#{delivery_id}", font=font_md, fill=(0, 0, 0))

    # Bottom-Right: STATUS
    draw.text((mid_x + 12, 523), "STATUS", font=font_xs, fill=(90, 90, 90))
    draw.text((mid_x + 12, 542), (status or "PENDING").upper()[:16], font=font_md, fill=(0, 0, 0))

    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out.read()
