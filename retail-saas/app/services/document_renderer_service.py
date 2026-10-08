import io
import logging
import re
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, Optional

import qrcode
import html
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    HRFlowable,
    Table as PlatyTable,
    TableStyle as PlatyTableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from app.core.exceptions import AppException
from app.schemas.document_setting import BrandingContext
from app.services.export_theme import THEMES, get_theme_for_report
from app.utils.helpers import amount_to_indian_words

logger = logging.getLogger(__name__)


def _xml_escape(text: Any) -> str:
    """Escapes XML/HTML special characters for safe ReportLab Platypus Paragraph formatting."""
    if text is None:
        return ""
    return html.escape(str(text), quote=False)


def format_document_number(raw_number: Any, prefix: Optional[str] = None, doc_type: str = "invoice") -> str:
    """
    Safely composes or adapts document numbers to prevent duplicate prefix composition
    such as DM-BILL--INV-2026-000004 or DM-INV--INV-2026-000004.
    """
    raw = str(raw_number or "").strip()
    if not raw:
        return ""
    if not prefix:
        return raw

    clean_prefix = prefix.rstrip("-_").strip()
    if not clean_prefix:
        return raw

    # If raw already starts with clean_prefix-
    if raw.startswith(f"{clean_prefix}-") or raw == clean_prefix:
        return raw

    # If raw already has a standard prefix structure like ABC-2026-000001, replace with clean_prefix
    m = re.match(r"^[A-Za-z0-9_]+[-_]+(\d{4}[-_]\d+)$", raw)
    if m:
        return f"{clean_prefix}-{m.group(1)}"

    # If raw has year-sequence like 2026-000001
    m2 = re.match(r"^(\d{4}[-_]\d+)$", raw)
    if m2:
        return f"{clean_prefix}-{m2.group(1)}"

    return f"{clean_prefix}-{raw}"


class RendererError(AppException):
    """Exception raised for errors during document rendering."""
    def __init__(self, message: str):
        super().__init__(status_code=500, detail=message)



class DocumentRenderer:
    def __init__(self):
        self.default_font = "Helvetica"
        self.bold_font = "Helvetica-Bold"
        self._register_fonts()

    def _register_fonts(self):
        """Register custom fonts for Unicode and Marathi/Devanagari support."""
        candidate_fonts = [
            Path("C:/Windows/Fonts/mangal.ttf"),
            Path("C:/Windows/Fonts/aparaj.ttf"),
            Path("C:/Windows/Fonts/kokila.ttf"),
            Path("C:/Windows/Fonts/Nirmala.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
            Path(__file__).parents[2] / "fonts" / "NotoSansDevanagari-Regular.ttf",
        ]
        candidate_bold_fonts = [
            Path("C:/Windows/Fonts/mangalb.ttf"),
            Path("C:/Windows/Fonts/aparajb.ttf"),
            Path("C:/Windows/Fonts/kokilab.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
            Path(__file__).parents[2] / "fonts" / "NotoSansDevanagari-Bold.ttf",
        ]

        self.has_devanagari_font = False
        self.has_devanagari_bold = False

        for font_path in candidate_fonts:
            if font_path.is_file():
                try:
                    pdfmetrics.registerFont(TTFont("Devanagari", str(font_path)))
                    self.has_devanagari_font = True
                    break
                except Exception as e:
                    logger.debug(f"Could not register Devanagari font {font_path}: {e}")

        for bold_path in candidate_bold_fonts:
            if bold_path.is_file():
                try:
                    pdfmetrics.registerFont(TTFont("Devanagari-Bold", str(bold_path)))
                    self.has_devanagari_bold = True
                    break
                except Exception as e:
                    logger.debug(f"Could not register Devanagari-Bold font {bold_path}: {e}")

    def _get_font(self, text: Optional[str], bold: bool = False) -> str:
        """Returns the appropriate font name based on text content (Unicode vs Latin)."""
        if text and any('\u0900' <= ch <= '\u097F' for ch in str(text)):
            if self.has_devanagari_font:
                return "Devanagari-Bold" if (bold and self.has_devanagari_bold) else "Devanagari"
        return self.bold_font if bold else self.default_font

    def _validate_logo_path(self, logo_url: Optional[str]) -> Optional[str]:
        """Validates and securely resolves logo file paths.
        Enforces security:
        - Must reside inside the project's configured uploads directory
        - Must be PNG, JPG, or JPEG
        - Rejects path traversal and external URLs
        """
        if not logo_url:
            return None

        clean_url = str(logo_url).strip()
        if not clean_url or clean_url.startswith("http://") or clean_url.startswith("https://"):
            return None

        uploads_root = (Path("uploads")).resolve()

        rel_str = clean_url
        if rel_str.startswith("/uploads/"):
            rel_str = rel_str[len("/uploads/"):]
        elif rel_str.startswith("uploads/"):
            rel_str = rel_str[len("uploads/"):]
        elif rel_str.startswith("/"):
            rel_str = rel_str.lstrip("/")

        try:
            resolved_path = (uploads_root / rel_str).resolve()
        except Exception as e:
            logger.warning(f"Error resolving logo path: {e}")
            return None

        # Enforce boundary within uploads directory
        try:
            if not resolved_path.is_relative_to(uploads_root):
                logger.warning(f"Path traversal detected in logo path: {logo_url}")
                return None
        except AttributeError:
            if not str(resolved_path).startswith(str(uploads_root)):
                return None

        if not resolved_path.is_file():
            logger.warning(f"Logo file does not exist at path: {resolved_path}")
            return None

        if resolved_path.suffix.lower() not in [".png", ".jpg", ".jpeg"]:
            logger.warning(f"Logo file has invalid extension: {resolved_path.suffix}")
            return None

        return str(resolved_path)

    def render(self, template_type: str, data: Dict[str, Any], branding: BrandingContext) -> bytes:
        """
        Main entry point for document rendering.
        Dispatches to specific renderers based on template_type.
        Supports both 'invoice' and 'invoice.html', 'bill' and 'bill.html'.
        """
        clean_type = (template_type or "").lower().replace(".html", "").strip()
        try:
            if clean_type == "invoice":
                return self._render_invoice(data, branding)
            elif clean_type in ("bill", "receipt"):
                return self._render_bill(data, branding)
            elif clean_type in ("credit_note", "credit-note"):
                return self._render_credit_note(data, branding)
            elif clean_type in ("purchase_order", "purchase-order", "po"):
                return self._render_purchase_order(data, branding)
            else:
                raise RendererError(f"Unsupported template type: {template_type}")
        except RendererError:
            raise
        except Exception as e:
            logger.error(f"Error rendering PDF: {str(e)}", exc_info=True)
            raise RendererError("Failed to generate PDF document due to an internal error.")

    def _render_invoice(self, data: Dict[str, Any], branding: BrandingContext) -> bytes:
        """Renders a formal A4 Tax Invoice PDF using ReportLab with corporate blue theme."""
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
        self._draw_tax_invoice(c, data, branding)
        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    def _render_bill(self, data: Dict[str, Any], branding: BrandingContext) -> bytes:
        """Renders a retail POS-style A4 Bill / Receipt PDF with emerald green theme."""
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
        self._draw_bill_receipt(c, data, branding)
        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    def _draw_tax_invoice(self, c: canvas.Canvas, data: Dict[str, Any], branding: BrandingContext):
        """Draws a formal Tax Invoice with corporate blue styling, Seller/Buyer cards, and detailed GST breakdown."""
        width, height = A4
        margin = 40
        y = height - margin

        primary_color = colors.HexColor("#1F497D")       # Corporate Navy Blue
        box_bg = colors.HexColor("#F0F4F8")              # Light blue-gray fill
        border_color = colors.HexColor("#CBD5E1")        # Slate border
        text_dark = colors.HexColor("#1E293B")           # Deep slate text
        text_muted = colors.HexColor("#64748B")          # Secondary text

        # 1. Top Header: Logo & Seller Details
        logo_path = self._validate_logo_path(branding.logo_url)
        if logo_path:
            try:
                img = ImageReader(logo_path)
                img_w, img_h = img.getSize()
                aspect = img_w / float(img_h)
                draw_w = min(100, 48 * aspect)
                draw_h = draw_w / aspect
                c.drawImage(img, width - margin - draw_w, y - draw_h + 10, width=draw_w, height=draw_h)
            except Exception as e:
                logger.warning(f"Failed to draw logo: {e}")

        # Seller Business Name
        c.setFont(self._get_font(branding.business_name, True), 16)
        c.setFillColor(primary_color)
        c.drawString(margin, y, branding.business_name or "Retail Store")
        y -= 18

        c.setFont(self._get_font(branding.address, False), 9)
        c.setFillColor(text_dark)
        if branding.address:
            c.drawString(margin, y, branding.address[:75])
            y -= 14

        contact_info = []
        if branding.phone:
            contact_info.append(f"Tel: {branding.phone}")
        if branding.email:
            contact_info.append(f"Email: {branding.email}")
        if branding.website:
            contact_info.append(f"Web: {branding.website}")
        if contact_info:
            c.setFont(self.default_font, 8.5)
            c.setFillColor(text_muted)
            c.drawString(margin, y, " | ".join(contact_info))
            y -= 14

        if branding.show_gstin and branding.gstin:
            c.setFont(self.bold_font, 9)
            c.setFillColor(primary_color)
            c.drawString(margin, y, f"GSTIN: {branding.gstin}")
            y -= 16

        y -= 6

        # 2. Title Banner: TAX INVOICE
        banner_height = 22
        c.setFillColor(primary_color)
        c.rect(margin, y - banner_height, width - 2 * margin, banner_height, fill=1, stroke=0)
        c.setFont(self.bold_font, 12)
        c.setFillColor(colors.white)
        c.drawCentredString(width / 2.0, y - banner_height + 6, "TAX INVOICE")
        y -= (banner_height + 10)

        # 3. Document Metadata Bar
        invoice_num = data.get("invoice_number", "")
        doc_no = format_document_number(invoice_num, branding.invoice_prefix, "invoice")

        meta_box_h = 42
        c.setFillColor(box_bg)
        c.setStrokeColor(border_color)
        c.rect(margin, y - meta_box_h, width - 2 * margin, meta_box_h, fill=1, stroke=1)

        c.setFillColor(text_dark)
        c.setFont(self.bold_font, 9)
        c.drawString(margin + 10, y - 14, f"Invoice No: {doc_no}")

        created_at_val = data.get("created_at")
        date_str = ""
        if created_at_val:
            date_str = created_at_val.strftime("%d-%m-%Y") if hasattr(created_at_val, "strftime") else str(created_at_val)[:10]
            c.drawString(margin + 200, y - 14, f"Date: {date_str}")

        order_no = data.get("order_number")
        if order_no:
            c.drawString(margin + 330, y - 14, f"Ref / Order: {order_no}")

        inv_type = "B2B Tax Invoice" if data.get("is_b2b") else "B2C Retail Invoice"
        c.setFont(self.default_font, 8.5)
        c.drawString(margin + 10, y - 30, f"Category: {inv_type}")
        payment_status = str(data.get("payment_status", "PAID")).upper()
        c.drawString(margin + 200, y - 30, f"Payment Status: {payment_status}")

        # QR Code on top right of metadata if enabled
        if branding.show_qr and data.get("qr_data"):
            try:
                qr = qrcode.QRCode(box_size=3, border=1)
                qr.add_data(data.get("qr_data"))
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                qr_buf = io.BytesIO()
                img.save(qr_buf, format="PNG")
                qr_buf.seek(0)
                qr_reader = ImageReader(qr_buf)
                c.drawImage(qr_reader, width - margin - 40, y - meta_box_h + 3, width=36, height=36)
            except Exception as e:
                logger.warning(f"Failed to draw QR code: {e}")

        y -= (meta_box_h + 12)

        # 4. Structured Seller & Buyer Cards
        card_w = (width - 2 * margin - 15) / 2.0
        card_h = 58
        # Seller Card (Left)
        c.setFillColor(colors.HexColor("#FAFAFA"))
        c.setStrokeColor(border_color)
        c.rect(margin, y - card_h, card_w, card_h, fill=1, stroke=1)
        c.setFillColor(primary_color)
        c.setFont(self.bold_font, 9)
        c.drawString(margin + 8, y - 14, "SELLER DETAILS")
        c.setFillColor(text_dark)
        c.setFont(self._get_font(branding.business_name, False), 8.5)
        c.drawString(margin + 8, y - 27, (branding.business_name or "")[:35])
        c.setFont(self.default_font, 8)
        if branding.phone:
            c.drawString(margin + 8, y - 39, f"Phone: {branding.phone}")
        if branding.show_gstin and branding.gstin:
            c.drawString(margin + 8, y - 50, f"GSTIN: {branding.gstin}")

        # Buyer Card (Right)
        customer = data.get("customer") or {}
        c.setFillColor(colors.HexColor("#FAFAFA"))
        c.setStrokeColor(border_color)
        c.rect(margin + card_w + 15, y - card_h, card_w, card_h, fill=1, stroke=1)
        c.setFillColor(primary_color)
        c.setFont(self.bold_font, 9)
        c.drawString(margin + card_w + 23, y - 14, "BILLED TO (BUYER)")
        c.setFillColor(text_dark)
        cust_name = customer.get("name") or "Walk-in Customer"
        c.setFont(self._get_font(cust_name, False), 8.5)
        c.drawString(margin + card_w + 23, y - 27, cust_name[:35])
        c.setFont(self.default_font, 8)
        cust_phone = customer.get("phone") or ""
        if cust_phone:
            c.drawString(margin + card_w + 23, y - 39, f"Mobile: {cust_phone}")
        cust_gstin = customer.get("gstin") or ""
        if cust_gstin:
            c.drawString(margin + card_w + 23, y - 50, f"GSTIN: {cust_gstin}")
        elif customer.get("address"):
            c.drawString(margin + card_w + 23, y - 50, customer.get("address")[:35])

        y -= (card_h + 14)

        # 5. Items Table Header
        def _draw_inv_table_header(curr_y: float) -> float:
            c.setFillColor(primary_color)
            c.rect(margin, curr_y - 16, width - 2 * margin, 16, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont(self.bold_font, 8.5)
            c.drawString(margin + 5, curr_y - 12, "#")
            c.drawString(margin + 25, curr_y - 12, "Item Description")
            c.drawString(margin + 200, curr_y - 12, "HSN")
            c.drawString(margin + 245, curr_y - 12, "Qty")
            c.drawString(margin + 280, curr_y - 12, "Price")
            c.drawString(margin + 330, curr_y - 12, "Disc")
            c.drawString(margin + 375, curr_y - 12, "GST")
            c.drawString(margin + 440, curr_y - 12, "Total")
            return curr_y - 22

        y = _draw_inv_table_header(y)

        # 6. Items Table Rows
        items = data.get("items", [])
        for idx, item in enumerate(items, start=1):
            if y < 140:
                self._draw_footer(c, branding)
                c.showPage()
                y = height - margin
                y = _draw_inv_table_header(y)

            if idx % 2 == 0:
                c.setFillColor(colors.HexColor("#F8FAFC"))
                c.rect(margin, y - 11, width - 2 * margin, 14, fill=1, stroke=0)

            c.setFillColor(text_dark)
            c.setFont(self.default_font, 8.5)
            c.drawString(margin + 5, y - 8, str(idx))

            p_name = str(item.get("product_name") or item.get("description") or "Item")
            c.setFont(self._get_font(p_name, False), 8.5)
            c.drawString(margin + 25, y - 8, p_name[:30])

            c.setFont(self.default_font, 8.5)
            c.drawString(margin + 200, y - 8, str(item.get("hsn_code") or ""))
            c.drawString(margin + 245, y - 8, str(item.get("quantity") or 1))

            unit_price = float(item.get("unit_price") or item.get("rate") or item.get("amount") or 0)
            disc = float(item.get("discount_amount") or item.get("discount") or 0)
            gst = float(item.get("gst_amount") or item.get("tax") or 0)
            line_total = float(item.get("total_amount") or item.get("total") or 0)

            c.drawString(margin + 280, y - 8, f"{unit_price:.2f}")
            c.drawString(margin + 330, y - 8, f"{disc:.2f}")
            c.drawString(margin + 375, y - 8, f"{gst:.2f}")
            c.drawString(margin + 440, y - 8, f"{line_total:.2f}")

            y -= 14

        c.setStrokeColor(border_color)
        c.line(margin, y, width - margin, y)
        y -= 14

        # 7. Financial Summary Box (Right Aligned)
        totals_x = margin + 320
        c.setFont(self.bold_font, 9)
        c.setFillColor(text_dark)

        subtotal_val = float(data.get("subtotal") if data.get("subtotal") is not None else (data.get("total") or 0))
        c.drawString(totals_x, y, "Subtotal (Taxable):")
        c.drawRightString(width - margin - 5, y, f"{subtotal_val:.2f}")
        y -= 13

        if data.get("discount_amount"):
            disc_val = float(data["discount_amount"])
            c.drawString(totals_x, y, "Total Discount:")
            c.drawRightString(width - margin - 5, y, f"-{disc_val:.2f}")
            y -= 13

        if data.get("cgst_amount"):
            cgst_val = float(data["cgst_amount"])
            c.drawString(totals_x, y, "CGST:")
            c.drawRightString(width - margin - 5, y, f"{cgst_val:.2f}")
            y -= 13

        if data.get("sgst_amount"):
            sgst_val = float(data["sgst_amount"])
            c.drawString(totals_x, y, "SGST:")
            c.drawRightString(width - margin - 5, y, f"{sgst_val:.2f}")
            y -= 13

        if data.get("igst_amount"):
            igst_val = float(data["igst_amount"])
            c.drawString(totals_x, y, "IGST:")
            c.drawRightString(width - margin - 5, y, f"{igst_val:.2f}")
            y -= 13

        # Grand Total Highlight Box
        grand_total = float(data.get("total_amount") if data.get("total_amount") is not None else (data.get("total") or 0))
        c.setFillColor(primary_color)
        c.rect(totals_x - 5, y - 16, (width - margin) - (totals_x - 5), 18, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(self.bold_font, 10)
        c.drawString(totals_x, y - 12, "Grand Total:")
        c.drawRightString(width - margin - 5, y - 12, f"{grand_total:.2f}")
        y -= 26

        # 8. Amount in Words
        c.setFillColor(text_dark)
        words = amount_to_indian_words(Decimal(str(grand_total)))
        c.setFont(self.bold_font, 8.5)
        c.drawString(margin, y, "Amount in Words:")
        c.setFont(self.default_font, 8.5)
        c.drawString(margin + 90, y, words)
        y -= 16

        # 9. Payment Details
        if branding.show_payment_details:
            payments = data.get("payments", [])
            if payments:
                c.setFont(self.bold_font, 8.5)
                c.drawString(margin, y, "Payment Details:")
                pay_strs = []
                for p in payments:
                    method = str(p.get("method") or p.get("payment_mode") or "Payment").upper()
                    amt = float(p.get("amount", 0))
                    ref = f" (Ref: {p['transaction_id']})" if p.get("transaction_id") else ""
                    pay_strs.append(f"{method}: {amt:.2f}{ref}")
                c.setFont(self.default_font, 8.5)
                c.drawString(margin + 80, y, " | ".join(pay_strs))
                y -= 16

        # 10. Terms and Signature
        if branding.footer_text:
            c.setFont(self.default_font, 8)
            c.setFillColor(text_muted)
            c.drawString(margin, y, f"Terms: {branding.footer_text[:90]}")

        if branding.show_signature:
            c.setFont(self.bold_font, 9)
            c.setFillColor(primary_color)
            c.drawRightString(width - margin, y - 10, "Authorized Signatory")
            c.setStrokeColor(primary_color)
            c.line(width - margin - 120, y - 13, width - margin, y - 13)

        self._draw_footer(c, branding)

    def _draw_bill_receipt(self, c: canvas.Canvas, data: Dict[str, Any], branding: BrandingContext):
        """Draws a compact retail POS Bill / Receipt with emerald green styling."""
        width, height = A4
        margin = 40
        y = height - margin

        primary_green = colors.HexColor("#1B5E20")       # Dark Emerald Green
        accent_green = colors.HexColor("#2E7D32")        # Emerald Accent
        fill_light_green = colors.HexColor("#E8F5E9")    # Light Green fill
        border_green = colors.HexColor("#A5D6A7")        # Soft green border
        text_dark = colors.HexColor("#1E293B")
        text_muted = colors.HexColor("#64748B")

        # 1. POS Retail Header
        logo_path = self._validate_logo_path(branding.logo_url)
        if logo_path:
            try:
                img = ImageReader(logo_path)
                img_w, img_h = img.getSize()
                aspect = img_w / float(img_h)
                draw_w = min(80, 40 * aspect)
                draw_h = draw_w / aspect
                c.drawImage(img, width - margin - draw_w, y - draw_h + 10, width=draw_w, height=draw_h)
            except Exception as e:
                logger.warning(f"Failed to draw logo: {e}")

        c.setFont(self._get_font(branding.business_name, True), 15)
        c.setFillColor(primary_green)
        c.drawString(margin, y, branding.business_name or "Retail Store")
        y -= 18

        c.setFont(self._get_font(branding.address, False), 9)
        c.setFillColor(text_dark)
        if branding.address:
            c.drawString(margin, y, branding.address[:75])
            y -= 14

        contact_info = []
        if branding.phone:
            contact_info.append(f"Tel: {branding.phone}")
        if branding.email:
            contact_info.append(f"Email: {branding.email}")
        if contact_info:
            c.setFont(self.default_font, 8.5)
            c.setFillColor(text_muted)
            c.drawString(margin, y, " | ".join(contact_info))
            y -= 14

        if branding.show_gstin and branding.gstin:
            c.setFont(self.bold_font, 8.5)
            c.setFillColor(primary_green)
            c.drawString(margin, y, f"GSTIN: {branding.gstin}")
            y -= 15

        y -= 6

        # 2. Title Banner: BILL / RECEIPT
        banner_height = 20
        c.setFillColor(accent_green)
        c.rect(margin, y - banner_height, width - 2 * margin, banner_height, fill=1, stroke=0)
        c.setFont(self.bold_font, 11)
        c.setFillColor(colors.white)
        c.drawCentredString(width / 2.0, y - banner_height + 5, "BILL / RECEIPT")
        y -= (banner_height + 10)

        # 3. Transaction Metadata Bar
        invoice_num = data.get("invoice_number", "")
        doc_no = format_document_number(invoice_num, branding.bill_prefix, "bill")

        meta_box_h = 32
        c.setFillColor(fill_light_green)
        c.setStrokeColor(border_green)
        c.rect(margin, y - meta_box_h, width - 2 * margin, meta_box_h, fill=1, stroke=1)

        c.setFillColor(text_dark)
        c.setFont(self.bold_font, 9)
        c.drawString(margin + 10, y - 13, f"Bill No: {doc_no}")

        created_at_val = data.get("created_at")
        date_str = ""
        if created_at_val:
            date_str = created_at_val.strftime("%d-%m-%Y %H:%M") if hasattr(created_at_val, "strftime") else str(created_at_val)[:16]
            c.drawString(margin + 180, y - 13, f"Date: {date_str}")

        customer = data.get("customer") or {}
        cust_name = customer.get("name") or "Walk-in Customer"
        c.setFont(self._get_font(cust_name, False), 8.5)
        c.drawString(margin + 330, y - 13, f"Customer: {cust_name[:25]}")

        # QR Code on top right if enabled
        if branding.show_qr and data.get("qr_data"):
            try:
                qr = qrcode.QRCode(box_size=3, border=1)
                qr.add_data(data.get("qr_data"))
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                qr_buf = io.BytesIO()
                img.save(qr_buf, format="PNG")
                qr_buf.seek(0)
                qr_reader = ImageReader(qr_buf)
                c.drawImage(qr_reader, width - margin - 35, y - meta_box_h + 2, width=30, height=30)
            except Exception as e:
                logger.warning(f"Failed to draw QR code: {e}")

        y -= (meta_box_h + 12)

        # 4. Compact Item Table Header
        def _draw_bill_table_header(curr_y: float) -> float:
            c.setFillColor(accent_green)
            c.rect(margin, curr_y - 15, width - 2 * margin, 15, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont(self.bold_font, 8.5)
            c.drawString(margin + 5, curr_y - 11, "#")
            c.drawString(margin + 25, curr_y - 11, "Item Name")
            c.drawString(margin + 210, curr_y - 11, "HSN")
            c.drawString(margin + 260, curr_y - 11, "Qty")
            c.drawString(margin + 300, curr_y - 11, "Price")
            c.drawString(margin + 350, curr_y - 11, "Disc")
            c.drawString(margin + 400, curr_y - 11, "Tax")
            c.drawString(margin + 450, curr_y - 11, "Total")
            return curr_y - 20

        y = _draw_bill_table_header(y)

        # 5. Items Table Rows
        items = data.get("items", [])
        for idx, item in enumerate(items, start=1):
            if y < 140:
                self._draw_footer(c, branding)
                c.showPage()
                y = height - margin
                y = _draw_bill_table_header(y)

            if idx % 2 == 0:
                c.setFillColor(colors.HexColor("#F9FBF9"))
                c.rect(margin, y - 10, width - 2 * margin, 13, fill=1, stroke=0)

            c.setFillColor(text_dark)
            c.setFont(self.default_font, 8.5)
            c.drawString(margin + 5, y - 8, str(idx))

            p_name = str(item.get("product_name") or item.get("description") or "Item")
            c.setFont(self._get_font(p_name, False), 8.5)
            c.drawString(margin + 25, y - 8, p_name[:32])

            c.setFont(self.default_font, 8.5)
            c.drawString(margin + 210, y - 8, str(item.get("hsn_code") or ""))
            c.drawString(margin + 260, y - 8, str(item.get("quantity") or 1))

            unit_price = float(item.get("unit_price") or item.get("rate") or item.get("amount") or 0)
            disc = float(item.get("discount_amount") or item.get("discount") or 0)
            gst = float(item.get("gst_amount") or item.get("tax") or 0)
            line_total = float(item.get("total_amount") or item.get("total") or 0)

            c.drawString(margin + 300, y - 8, f"{unit_price:.2f}")
            c.drawString(margin + 350, y - 8, f"{disc:.2f}")
            c.drawString(margin + 400, y - 8, f"{gst:.2f}")
            c.drawString(margin + 450, y - 8, f"{line_total:.2f}")

            y -= 13

        c.setStrokeColor(border_green)
        c.line(margin, y, width - margin, y)
        y -= 14

        # 6. Prominent Totals Summary Box
        totals_x = margin + 320
        c.setFont(self.bold_font, 9)
        c.setFillColor(text_dark)

        subtotal_val = float(data.get("subtotal") if data.get("subtotal") is not None else (data.get("total") or 0))
        c.drawString(totals_x, y, "Subtotal:")
        c.drawRightString(width - margin - 5, y, f"{subtotal_val:.2f}")
        y -= 13

        if data.get("discount_amount"):
            disc_val = float(data["discount_amount"])
            c.drawString(totals_x, y, "Discount:")
            c.drawRightString(width - margin - 5, y, f"-{disc_val:.2f}")
            y -= 13

        tax_sum = float(data.get("cgst_amount", 0) or 0) + float(data.get("sgst_amount", 0) or 0) + float(data.get("igst_amount", 0) or 0)
        if tax_sum > 0:
            c.drawString(totals_x, y, "Taxes (GST):")
            c.drawRightString(width - margin - 5, y, f"{tax_sum:.2f}")
            y -= 13

        grand_total = float(data.get("total_amount") if data.get("total_amount") is not None else (data.get("total") or 0))
        c.setFillColor(fill_light_green)
        c.setStrokeColor(accent_green)
        c.rect(totals_x - 5, y - 18, (width - margin) - (totals_x - 5), 20, fill=1, stroke=1)
        c.setFillColor(primary_green)
        c.setFont(self.bold_font, 11)
        c.drawString(totals_x, y - 13, "TOTAL AMOUNT:")
        c.drawRightString(width - margin - 5, y - 13, f"{grand_total:.2f}")
        y -= 28

        # 7. Payment Breakdown
        if branding.show_payment_details:
            payments = data.get("payments", [])
            if payments:
                c.setFont(self.bold_font, 8.5)
                c.drawString(margin, y, "Payment:")
                pay_strs = []
                for p in payments:
                    method = str(p.get("method") or p.get("payment_mode") or "Payment").upper()
                    amt = float(p.get("amount", 0))
                    ref = f" (Ref: {p['transaction_id']})" if p.get("transaction_id") else ""
                    pay_strs.append(f"{method}: {amt:.2f}{ref}")
                c.setFont(self.default_font, 8.5)
                c.drawString(margin + 55, y, " | ".join(pay_strs))
                y -= 16

        # 8. Friendly Retail Footer
        retail_note = branding.footer_text or "Thank you for shopping with us! Please visit again."
        c.setFont(self._get_font(retail_note, False), 8)
        c.setFillColor(text_muted)
        c.drawCentredString(width / 2.0, 32, retail_note)

    def render_report_pdf(
        self,
        report_title: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        kpis: Optional[list[Dict[str, Any]]] = None,
        headers: Optional[list[str]] = None,
        rows: Optional[list[list[Any]]] = None,
        branding: Optional[BrandingContext] = None,
        notes: Optional[str] = None,
        report_type: Optional[str] = None,
        **kwargs: Any,
    ) -> bytes:
        """
        Renders a production-grade branded Report PDF using ReportLab Platypus.
        Includes:
        - Corporate branded header (logo, business name, address, contact, GSTIN)
        - Dynamic report title and metadata parameters
        - KPI cards summary block (if kpis provided)
        - Professional styled data table with zebra striping and repeated headers
        - Clean running footer with page numbering
        """
        resolved_title = kwargs.get("title", report_title) or report_title or "Report"
        resolved_kpis = kwargs.get("kpi_summary", kpis) or kpis or []
        resolved_headers = headers or []
        resolved_rows = rows or []
        resolved_metadata = metadata or {}
        resolved_report_type = kwargs.get("report_type") or report_type

        theme = get_theme_for_report(resolved_report_type or resolved_title)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=40,
        )

        styles = getSampleStyleSheet()
        normal_style = styles["Normal"]

        elements = []

        # 1. Branded Company Header
        header_text = []
        biz_name = getattr(branding, "business_name", None) or "Retail Store"
        header_text.append(f"<font size='13' color='{theme.primary_hex}'><b>{_xml_escape(biz_name)}</b></font>")

        addr = getattr(branding, "address", None)
        if addr:
            header_text.append(f"<font size='8' color='#475569'>{_xml_escape(addr)}</font>")

        contact_parts = []
        phone = getattr(branding, "phone", None)
        if phone:
            contact_parts.append(f"Phone: {_xml_escape(phone)}")
        email = getattr(branding, "email", None)
        if email:
            contact_parts.append(f"Email: {_xml_escape(email)}")
        website = getattr(branding, "website", None)
        if website:
            contact_parts.append(f"Web: {_xml_escape(website)}")
        if contact_parts:
            header_text.append(f"<font size='8' color='#475569'>{' &nbsp;|&nbsp; '.join(contact_parts)}</font>")

        gstin = getattr(branding, "gstin", None)
        show_gstin = getattr(branding, "show_gstin", True)
        if show_gstin and gstin:
            header_text.append(f"<font size='8' color='#475569'><b>GSTIN:</b> {_xml_escape(gstin)}</font>")

        company_p = Paragraph("<br/>".join(header_text), normal_style)

        logo_url = getattr(branding, "logo_url", None)
        logo_path = self._validate_logo_path(logo_url)
        logo_img = None
        if logo_path:
            try:
                from reportlab.platypus import Image as PlatyImage
                img = ImageReader(logo_path)
                iw, ih = img.getSize()
                aspect = iw / float(ih)
                max_w = 75.0
                max_h = 45.0
                if aspect >= 1:
                    w = min(max_w, max_h * aspect)
                    h = w / aspect
                else:
                    h = min(max_h, max_w / aspect)
                    w = h * aspect
                logo_img = PlatyImage(logo_path, width=w, height=h)
            except Exception as e:
                logger.warning(f"Failed to embed logo in report: {e}")
                logo_img = None

        if logo_img:
            header_table = PlatyTable(
                [[logo_img, company_p]],
                colWidths=[80, 443],
            )
            header_table.setStyle(PlatyTableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "LEFT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            elements.append(header_table)
        else:
            elements.append(company_p)

        elements.append(Spacer(1, 4))
        elements.append(HRFlowable(width="100%", thickness=1, color=theme.primary_color, spaceBefore=2, spaceAfter=8))

        # 2. Report Title & Metadata Banner
        title_p = Paragraph(f"<font size='12' color='{theme.primary_hex}'><b>{_xml_escape(resolved_title.upper())}</b></font>", normal_style)
        elements.append(title_p)
        elements.append(Spacer(1, 4))

        if resolved_metadata:
            meta_items = [f"<b>{_xml_escape(k)}:</b> {_xml_escape(v) if v is not None else 'N/A'}" for k, v in resolved_metadata.items()]
            meta_str = " &nbsp;&nbsp;|&nbsp;&nbsp; ".join(meta_items)
            meta_p = Paragraph(f"<font size='8' color='#334155'>{meta_str}</font>", normal_style)
            elements.append(meta_p)
            elements.append(Spacer(1, 8))

        # 3. KPI Summary Cards (if available)
        if resolved_kpis:
            kpi_cells = []
            for item in resolved_kpis[:4]:
                lbl = item.get("label") or item.get("metric") or "Metric"
                val = item.get("value")
                if isinstance(val, (int, float, Decimal)):
                    val_str = f"{float(val):,.2f}" if isinstance(val, (float, Decimal)) else f"{val:,}"
                else:
                    val_str = str(val if val is not None else "")
                cell_p = Paragraph(
                    f"<para align='center'><font size='7.5' color='#64748B'>{lbl.upper()}</font><br/>"
                    f"<font size='11' color='{theme.primary_hex}'><b>{val_str}</b></font></para>",
                    normal_style,
                )
                kpi_cells.append(cell_p)

            num_kpis = len(kpi_cells)
            if num_kpis > 0:
                col_w = 523.0 / num_kpis
                kpi_table = PlatyTable([kpi_cells], colWidths=[col_w] * num_kpis)
                kpi_table.setStyle(PlatyTableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), theme.bg_light_color),
                    ("BOX", (0, 0), (-1, -1), 1, theme.border_color),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, theme.border_color),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]))
                elements.append(kpi_table)
                elements.append(Spacer(1, 12))

        # 4. Report Data Table
        if resolved_headers and resolved_rows:
            h_cells = [
                Paragraph(f"<font size='8.5' color='white'><b>{h}</b></font>", normal_style)
                for h in resolved_headers
            ]
            t_data = [h_cells]

            total_w = 523.0
            num_cols = len(resolved_headers)
            base_col_w = total_w / num_cols
            col_widths = [base_col_w] * num_cols

            for r in resolved_rows:
                r_cells = []
                for idx, c in enumerate(r):
                    val_s = str(c if c is not None else "")
                    if isinstance(c, (int, float, Decimal)):
                        if isinstance(c, (float, Decimal)):
                            formatted_val = f"{float(c):,.2f}"
                        else:
                            formatted_val = f"{c:,}"
                        p_cell = Paragraph(f"<para align='right'><font size='8' color='#1E293B'>{formatted_val}</font></para>", normal_style)
                    else:
                        p_cell = Paragraph(f"<font size='8' color='#1E293B'>{val_s}</font>", normal_style)
                    r_cells.append(p_cell)
                t_data.append(r_cells)

            report_table = PlatyTable(t_data, colWidths=col_widths, repeatRows=1)
            report_table.setStyle(PlatyTableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), theme.primary_color),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("GRID", (0, 0), (-1, -1), 0.5, theme.border_color),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, theme.bg_light_color]),
            ]))
            elements.append(report_table)

        if notes:
            elements.append(Spacer(1, 10))
            elements.append(Paragraph(f"<font size='7.5' color='#64748B'><i>Note: {notes}</i></font>", normal_style))

        def _add_footer(canvas_obj, document):
            canvas_obj.saveState()
            canvas_obj.setFont("Helvetica", 7.5)
            canvas_obj.setFillColor(colors.HexColor("#64748B"))
            canvas_obj.drawString(36, 20, "Generated by Retail-OS | Confidential")
            footer_text = getattr(branding, "footer_text", None)
            if footer_text:
                canvas_obj.drawCentredString(A4[0] / 2.0, 20, str(footer_text)[:60])
            page_str = f"Page {document.page}"
            canvas_obj.drawRightString(A4[0] - 36, 20, page_str)
            canvas_obj.restoreState()

        class UncompressedCanvas(canvas.Canvas):
            def __init__(self, *args, **kwargs):
                kwargs["pageCompression"] = 0
                super().__init__(*args, **kwargs)

        doc.build(elements, canvasmaker=UncompressedCanvas, onFirstPage=_add_footer, onLaterPages=_add_footer)
        buffer.seek(0)
        return buffer.getvalue()

    def _draw_footer(self, c: canvas.Canvas, branding: BrandingContext):
        """Draws the footer text at the bottom of the page."""
        width, height = A4
        if branding.footer_text:
            c.setFont(self._get_font(branding.footer_text, False), 8)
            c.drawCentredString(width / 2.0, 30, branding.footer_text)

    def _draw_document(self, c: canvas.Canvas, data: Dict[str, Any], branding: BrandingContext, title: str, prefix: str):
        """Backward-compatible helper that delegates to dedicated invoice/bill renderer based on title."""
        if "BILL" in (title or "").upper():
            self._draw_bill_receipt(c, data, branding)
        else:
            self._draw_tax_invoice(c, data, branding)


    def _render_credit_note(self, data: Dict[str, Any], branding: BrandingContext) -> bytes:
        """Renders an A4 credit note PDF using ReportLab."""
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
        self._draw_credit_note(c, data, branding)
        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    def _draw_credit_note(self, c: canvas.Canvas, data: Dict[str, Any], branding: BrandingContext):
        """Draws a branded GST Credit Note with Coral Red styling (#DC2626)."""
        width, height = A4
        margin = 40
        y = height - margin

        theme = THEMES["credit_note"]
        primary_color = theme.primary_color       # #DC2626 Coral Red
        box_bg = theme.bg_light_color             # #FEF2F2 Soft Red Tint
        border_color = theme.border_color         # #FECACA
        text_dark = colors.HexColor("#1E293B")
        text_muted = colors.HexColor("#64748B")

        # 1. Top Header: Logo & Issuer Business Details
        logo_path = self._validate_logo_path(branding.logo_url)
        if logo_path:
            try:
                img = ImageReader(logo_path)
                img_w, img_h = img.getSize()
                aspect = img_w / float(img_h)
                draw_w = min(100, 48 * aspect)
                draw_h = draw_w / aspect
                c.drawImage(img, width - margin - draw_w, y - draw_h + 10, width=draw_w, height=draw_h)
            except Exception as e:
                logger.warning(f"Failed to draw logo: {e}")

        c.setFont(self._get_font(branding.business_name, True), 16)
        c.setFillColor(primary_color)
        c.drawString(margin, y, branding.business_name or "Retail Store")
        y -= 18

        c.setFont(self._get_font(branding.address, False), 9)
        c.setFillColor(text_dark)
        if branding.address:
            c.drawString(margin, y, branding.address[:75])
            y -= 14

        contact_info = []
        if branding.phone:
            contact_info.append(f"Tel: {branding.phone}")
        if branding.email:
            contact_info.append(f"Email: {branding.email}")
        if branding.website:
            contact_info.append(f"Web: {branding.website}")
        if contact_info:
            c.setFont(self.default_font, 8.5)
            c.setFillColor(text_muted)
            c.drawString(margin, y, " | ".join(contact_info))
            y -= 14

        if branding.show_gstin and branding.gstin:
            c.setFont(self.bold_font, 9)
            c.setFillColor(primary_color)
            c.drawString(margin, y, f"GSTIN: {branding.gstin}")
            y -= 16

        y -= 6

        # 2. Title Banner: CREDIT NOTE
        banner_height = 22
        c.setFillColor(primary_color)
        c.rect(margin, y - banner_height, width - 2 * margin, banner_height, fill=1, stroke=0)
        c.setFont(self.bold_font, 12)
        c.setFillColor(colors.white)
        c.drawCentredString(width / 2.0, y - banner_height + 6, "CREDIT NOTE")
        y -= (banner_height + 10)

        # 3. Document Metadata Bar
        cn_raw = data.get("credit_note_no") or data.get("credit_note_number", "")
        cn_number = format_document_number(cn_raw, branding.invoice_prefix, "credit_note")

        meta_box_h = 42
        c.setFillColor(box_bg)
        c.setStrokeColor(border_color)
        c.rect(margin, y - meta_box_h, width - 2 * margin, meta_box_h, fill=1, stroke=1)

        c.setFillColor(text_dark)
        c.setFont(self.bold_font, 9)
        c.drawString(margin + 10, y - 14, f"Credit Note No: {cn_number}")

        created_at_val = data.get("created_at")
        date_str = ""
        if created_at_val:
            date_str = created_at_val.strftime("%d-%m-%Y") if hasattr(created_at_val, "strftime") else str(created_at_val)[:10]
            c.drawString(margin + 200, y - 14, f"Date: {date_str}")

        orig_inv = data.get("original_invoice_number") or data.get("invoice_number", "")
        c.setFont(self.default_font, 8.5)
        c.drawString(margin + 10, y - 30, f"Against Invoice: {orig_inv or 'N/A'}")

        reason = str(data.get("reason") or "Returned goods / adjustment")
        c.drawString(margin + 200, y - 30, f"Reason: {reason[:45]}")

        # QR Code if enabled
        if branding.show_qr and data.get("qr_data"):
            try:
                qr = qrcode.QRCode(box_size=3, border=1)
                qr.add_data(data.get("qr_data"))
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                qr_buf = io.BytesIO()
                img.save(qr_buf, format="PNG")
                qr_buf.seek(0)
                qr_reader = ImageReader(qr_buf)
                c.drawImage(qr_reader, width - margin - 40, y - meta_box_h + 3, width=36, height=36)
            except Exception as e:
                logger.warning(f"Failed to draw QR code: {e}")

        y -= (meta_box_h + 12)

        # 4. Structured Issuer & Buyer Cards
        card_w = (width - 2 * margin - 15) / 2.0
        card_h = 58
        # Issuer Card (Left)
        c.setFillColor(colors.HexColor("#FAFAFA"))
        c.setStrokeColor(border_color)
        c.rect(margin, y - card_h, card_w, card_h, fill=1, stroke=1)
        c.setFillColor(primary_color)
        c.setFont(self.bold_font, 9)
        c.drawString(margin + 8, y - 14, "ISSUED BY (SELLER)")
        c.setFillColor(text_dark)
        c.setFont(self._get_font(branding.business_name, False), 8.5)
        c.drawString(margin + 8, y - 27, (branding.business_name or "")[:35])
        c.setFont(self.default_font, 8)
        if branding.phone:
            c.drawString(margin + 8, y - 39, f"Phone: {branding.phone}")
        if branding.show_gstin and branding.gstin:
            c.drawString(margin + 8, y - 50, f"GSTIN: {branding.gstin}")

        # Buyer Card (Right)
        customer = data.get("customer") or {}
        c.setFillColor(colors.HexColor("#FAFAFA"))
        c.setStrokeColor(border_color)
        c.rect(margin + card_w + 15, y - card_h, card_w, card_h, fill=1, stroke=1)
        c.setFillColor(primary_color)
        c.setFont(self.bold_font, 9)
        c.drawString(margin + card_w + 23, y - 14, "CREDIT ISSUED TO (BUYER)")
        c.setFillColor(text_dark)
        cust_name = customer.get("name") or "Valued Customer"
        c.setFont(self._get_font(cust_name, False), 8.5)
        c.drawString(margin + card_w + 23, y - 27, cust_name[:35])
        c.setFont(self.default_font, 8)
        cust_phone = customer.get("phone") or ""
        if cust_phone:
            c.drawString(margin + card_w + 23, y - 39, f"Mobile: {cust_phone}")
        cust_gstin = customer.get("gstin") or ""
        if cust_gstin:
            c.drawString(margin + card_w + 23, y - 50, f"GSTIN: {cust_gstin}")
        elif customer.get("address"):
            c.drawString(margin + card_w + 23, y - 50, customer.get("address")[:35])

        y -= (card_h + 14)

        # 5. Items / Adjustments Table Header
        items = data.get("items", [])
        refund_amount = float(data.get("refund_amount", 0))
        cgst_val = float(data.get("cgst_amount", 0) or 0)
        sgst_val = float(data.get("sgst_amount", 0) or 0)
        igst_val = float(data.get("igst_amount", 0) or 0)
        tax_total = cgst_val + sgst_val + igst_val
        total_credit = refund_amount + tax_total if tax_total > 0 and (refund_amount > 0 and abs(refund_amount - float(data.get("total_amount", refund_amount))) > 0.01) else refund_amount

        def _draw_cn_table_header(curr_y: float) -> float:
            c.setFillColor(primary_color)
            c.rect(margin, curr_y - 16, width - 2 * margin, 16, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont(self.bold_font, 8.5)
            c.drawString(margin + 5, curr_y - 12, "#")
            c.drawString(margin + 25, curr_y - 12, "Description / Component")
            c.drawString(margin + 220, curr_y - 12, "HSN / SAC")
            c.drawString(margin + 280, curr_y - 12, "Qty / Rate")
            c.drawString(margin + 360, curr_y - 12, "Tax Adj")
            c.drawString(margin + 440, curr_y - 12, "Credit (INR)")
            return curr_y - 22

        y = _draw_cn_table_header(y)

        # 6. Items / Adjustment Rows
        if items:
            for idx, item in enumerate(items, start=1):
                if y < 140:
                    self._draw_footer(c, branding)
                    c.showPage()
                    y = height - margin
                    y = _draw_cn_table_header(y)

                if idx % 2 == 0:
                    c.setFillColor(colors.HexColor("#FEF2F2"))
                    c.rect(margin, y - 11, width - 2 * margin, 14, fill=1, stroke=0)

                c.setFillColor(text_dark)
                c.setFont(self.default_font, 8.5)
                c.drawString(margin + 5, y - 8, str(idx))

                p_name = str(item.get("product_name") or item.get("description") or "Item")
                c.setFont(self._get_font(p_name, False), 8.5)
                c.drawString(margin + 25, y - 8, p_name[:32])

                c.setFont(self.default_font, 8.5)
                c.drawString(margin + 220, y - 8, str(item.get("hsn_code") or ""))
                qty = item.get("quantity") or 1
                price = float(item.get("unit_price") or 0)
                c.drawString(margin + 280, y - 8, f"{qty} x {price:.2f}")

                tax_adj = float(item.get("gst_amount") or item.get("tax") or 0)
                line_total = float(item.get("total_amount") or item.get("total") or 0)
                c.drawString(margin + 360, y - 8, f"{tax_adj:.2f}")
                c.drawString(margin + 440, y - 8, f"{line_total:.2f}")
                y -= 14
        else:
            # Standalone credit adjustment breakdown
            row_items = [
                ("1", "Goods Return / Refund Value", "9983", "1", "-", refund_amount),
            ]
            if cgst_val > 0:
                row_items.append(("2", "CGST Credit Adjustment", "9983", "-", f"{cgst_val:.2f}", cgst_val))
            if sgst_val > 0:
                row_items.append(("3", "SGST Credit Adjustment", "9983", "-", f"{sgst_val:.2f}", sgst_val))
            if igst_val > 0:
                row_items.append(("4", "IGST Credit Adjustment", "9983", "-", f"{igst_val:.2f}", igst_val))

            for r_idx, (r_num, r_desc, r_hsn, r_rate, r_tax, r_amt) in enumerate(row_items):
                if r_idx % 2 == 1:
                    c.setFillColor(colors.HexColor("#FEF2F2"))
                    c.rect(margin, y - 11, width - 2 * margin, 14, fill=1, stroke=0)

                c.setFillColor(text_dark)
                c.setFont(self.default_font, 8.5)
                c.drawString(margin + 5, y - 8, r_num)
                c.drawString(margin + 25, y - 8, r_desc)
                c.drawString(margin + 220, y - 8, r_hsn)
                c.drawString(margin + 280, y - 8, r_rate)
                c.drawString(margin + 360, y - 8, r_tax)
                c.drawString(margin + 440, y - 8, f"{r_amt:.2f}")
                y -= 14

        c.setStrokeColor(border_color)
        c.line(margin, y, width - margin, y)
        y -= 14

        # 7. Financial Summary Box (Right Aligned)
        totals_x = margin + 310
        c.setFont(self.bold_font, 9)
        c.setFillColor(text_dark)

        c.drawString(totals_x, y, "Base Refund Value:")
        c.drawRightString(width - margin - 5, y, f"{refund_amount:.2f}")
        y -= 13

        if cgst_val > 0:
            c.drawString(totals_x, y, "CGST Credit:")
            c.drawRightString(width - margin - 5, y, f"{cgst_val:.2f}")
            y -= 13

        if sgst_val > 0:
            c.drawString(totals_x, y, "SGST Credit:")
            c.drawRightString(width - margin - 5, y, f"{sgst_val:.2f}")
            y -= 13

        if igst_val > 0:
            c.drawString(totals_x, y, "IGST Credit:")
            c.drawRightString(width - margin - 5, y, f"{igst_val:.2f}")
            y -= 13

        # Prominent Red Grand Total Box
        c.setFillColor(primary_color)
        c.rect(totals_x - 5, y - 16, (width - margin) - (totals_x - 5), 18, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(self.bold_font, 10)
        c.drawString(totals_x, y - 12, "Total Credited Amount:")
        c.drawRightString(width - margin - 5, y - 12, f"{refund_amount:.2f}")
        y -= 26

        # 8. Amount in Words
        c.setFillColor(text_dark)
        words = amount_to_indian_words(Decimal(str(refund_amount)))
        c.setFont(self.bold_font, 8.5)
        c.drawString(margin, y, "Amount in Words:")
        c.setFont(self.default_font, 8.5)
        c.drawString(margin + 90, y, words)
        y -= 16

        # 9. Terms and Signatory
        if branding.footer_text:
            c.setFont(self.default_font, 8)
            c.setFillColor(text_muted)
            c.drawString(margin, y, f"Remarks: {branding.footer_text[:90]}")

        if branding.show_signature:
            c.setFont(self.bold_font, 9)
            c.setFillColor(primary_color)
            c.drawRightString(width - margin, y - 10, "Authorized Signatory")
            c.setStrokeColor(primary_color)
            c.line(width - margin - 120, y - 13, width - margin, y - 13)

        self._draw_footer(c, branding)

    def _render_purchase_order(self, data: Dict[str, Any], branding: BrandingContext) -> bytes:
        """Renders an A4 purchase order PDF using ReportLab with purple indigo theme."""
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
        self._draw_purchase_order(c, data, branding)
        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    def _draw_purchase_order(self, c: canvas.Canvas, data: Dict[str, Any], branding: BrandingContext):
        """Draws a branded Purchase Order for vendors with Purple/Indigo styling (#6D28D9)."""
        width, height = A4
        margin = 40
        y = height - margin

        theme = THEMES["purchase_order"]
        primary_color = theme.primary_color       # #6D28D9 Purple Indigo
        box_bg = theme.bg_light_color             # #FAF5FF Soft Purple Tint
        border_color = theme.border_color         # #E9D5FF
        text_dark = colors.HexColor("#1E293B")
        text_muted = colors.HexColor("#64748B")

        # 1. Top Header: Logo & Buyer Business Details
        logo_path = self._validate_logo_path(branding.logo_url)
        if logo_path:
            try:
                img = ImageReader(logo_path)
                img_w, img_h = img.getSize()
                aspect = img_w / float(img_h)
                draw_w = min(100, 48 * aspect)
                draw_h = draw_w / aspect
                c.drawImage(img, width - margin - draw_w, y - draw_h + 10, width=draw_w, height=draw_h)
            except Exception as e:
                logger.warning(f"Failed to draw logo: {e}")

        c.setFont(self._get_font(branding.business_name, True), 16)
        c.setFillColor(primary_color)
        c.drawString(margin, y, branding.business_name or "Retail Store")
        y -= 18

        c.setFont(self._get_font(branding.address, False), 9)
        c.setFillColor(text_dark)
        if branding.address:
            c.drawString(margin, y, branding.address[:75])
            y -= 14

        contact_info = []
        if branding.phone:
            contact_info.append(f"Tel: {branding.phone}")
        if branding.email:
            contact_info.append(f"Email: {branding.email}")
        if branding.website:
            contact_info.append(f"Web: {branding.website}")
        if contact_info:
            c.setFont(self.default_font, 8.5)
            c.setFillColor(text_muted)
            c.drawString(margin, y, " | ".join(contact_info))
            y -= 14

        if branding.show_gstin and branding.gstin:
            c.setFont(self.bold_font, 9)
            c.setFillColor(primary_color)
            c.drawString(margin, y, f"GSTIN: {branding.gstin}")
            y -= 16

        y -= 6

        # 2. Title Banner: PURCHASE ORDER
        banner_height = 22
        c.setFillColor(primary_color)
        c.rect(margin, y - banner_height, width - 2 * margin, banner_height, fill=1, stroke=0)
        c.setFont(self.bold_font, 12)
        c.setFillColor(colors.white)
        c.drawCentredString(width / 2.0, y - banner_height + 6, "PURCHASE ORDER")
        y -= (banner_height + 10)

        # 3. Document Details Box
        po_raw = data.get("order_number") or data.get("po_number", "")
        po_number = format_document_number(po_raw, "PO", "purchase_order")

        meta_box_h = 42
        c.setFillColor(box_bg)
        c.setStrokeColor(border_color)
        c.rect(margin, y - meta_box_h, width - 2 * margin, meta_box_h, fill=1, stroke=1)

        c.setFillColor(text_dark)
        c.setFont(self.bold_font, 9)
        c.drawString(margin + 10, y - 14, f"PO Number: {po_number}")

        order_date_val = data.get("order_date") or data.get("created_at")
        date_str = ""
        if order_date_val:
            date_str = order_date_val.strftime("%d-%m-%Y") if hasattr(order_date_val, "strftime") else str(order_date_val)[:10]
            c.drawString(margin + 200, y - 14, f"Date: {date_str}")

        po_status = str(data.get("status") or "CONFIRMED").upper()
        c.setFont(self.default_font, 8.5)
        c.drawString(margin + 10, y - 30, f"Status: {po_status}")
        c.drawString(margin + 200, y - 30, "Terms: Payment within 30 days of receipt")

        y -= (meta_box_h + 12)

        # 4. Structured Buyer & Supplier Cards
        card_w = (width - 2 * margin - 15) / 2.0
        card_h = 58
        # Buyer Card (Left)
        c.setFillColor(colors.HexColor("#FAFAFA"))
        c.setStrokeColor(border_color)
        c.rect(margin, y - card_h, card_w, card_h, fill=1, stroke=1)
        c.setFillColor(primary_color)
        c.setFont(self.bold_font, 9)
        c.drawString(margin + 8, y - 14, "BUYER (DELIVER TO)")
        c.setFillColor(text_dark)
        c.setFont(self._get_font(branding.business_name, False), 8.5)
        c.drawString(margin + 8, y - 27, (branding.business_name or "")[:35])
        c.setFont(self.default_font, 8)
        if branding.address:
            c.drawString(margin + 8, y - 39, branding.address[:35])
        if branding.show_gstin and branding.gstin:
            c.drawString(margin + 8, y - 50, f"GSTIN: {branding.gstin}")

        # Supplier Card (Right)
        supplier = data.get("supplier") or {}
        c.setFillColor(colors.HexColor("#FAFAFA"))
        c.setStrokeColor(border_color)
        c.rect(margin + card_w + 15, y - card_h, card_w, card_h, fill=1, stroke=1)
        c.setFillColor(primary_color)
        c.setFont(self.bold_font, 9)
        c.drawString(margin + card_w + 23, y - 14, "VENDOR / SUPPLIER")
        c.setFillColor(text_dark)
        supp_name = supplier.get("name") or "Vendor / Supplier"
        c.setFont(self._get_font(supp_name, False), 8.5)
        c.drawString(margin + card_w + 23, y - 27, supp_name[:35])
        c.setFont(self.default_font, 8)
        s_contact = " | ".join(filter(None, [supplier.get("phone"), supplier.get("email")]))
        if s_contact:
            c.drawString(margin + card_w + 23, y - 39, s_contact[:38])
        if supplier.get("gstin"):
            c.drawString(margin + card_w + 23, y - 50, f"GSTIN: {supplier.get('gstin')}")
        elif supplier.get("address"):
            c.drawString(margin + card_w + 23, y - 50, supplier.get("address")[:35])

        y -= (card_h + 14)

        # 5. Items Table Header
        def _draw_po_table_header(curr_y: float) -> float:
            c.setFillColor(primary_color)
            c.rect(margin, curr_y - 16, width - 2 * margin, 16, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont(self.bold_font, 8.5)
            c.drawString(margin + 5, curr_y - 12, "#")
            c.drawString(margin + 25, curr_y - 12, "Item Description")
            c.drawString(margin + 230, curr_y - 12, "SKU / Code")
            c.drawString(margin + 330, curr_y - 12, "Quantity")
            c.drawString(margin + 390, curr_y - 12, "Unit Cost")
            c.drawString(margin + 450, curr_y - 12, "Total (INR)")
            return curr_y - 22

        y = _draw_po_table_header(y)

        # 6. Items Rows
        items = data.get("items", [])
        for idx, it in enumerate(items, start=1):
            if y < 140:
                self._draw_footer(c, branding)
                c.showPage()
                y = height - margin
                y = _draw_po_table_header(y)

            if idx % 2 == 0:
                c.setFillColor(colors.HexColor("#FAF5FF"))
                c.rect(margin, y - 11, width - 2 * margin, 14, fill=1, stroke=0)

            c.setFillColor(text_dark)
            c.setFont(self.default_font, 8.5)
            c.drawString(margin + 5, y - 8, str(idx))

            it_name = str(it.get("product_name") or it.get("name") or "Product")
            c.setFont(self._get_font(it_name, False), 8.5)
            c.drawString(margin + 25, y - 8, it_name[:32])

            c.setFont(self.default_font, 8.5)
            c.drawString(margin + 230, y - 8, str(it.get("sku") or ""))
            qty = it.get("quantity") or 0
            c.drawString(margin + 330, y - 8, str(qty))

            uc = float(it.get("unit_cost") or 0)
            c.drawString(margin + 390, y - 8, f"{uc:.2f}")

            line_tot = float(it.get("total_cost") or (qty * uc))
            c.drawString(margin + 450, y - 8, f"{line_tot:.2f}")

            y -= 14

        c.setStrokeColor(border_color)
        c.line(margin, y, width - margin, y)
        y -= 14

        # 7. Total Summary Box
        totals_x = margin + 310
        total_amount = float(data.get("total_amount") or 0)

        c.setFont(self.bold_font, 9)
        c.setFillColor(text_dark)
        c.drawString(totals_x, y, "Total Items:")
        c.drawRightString(width - margin - 5, y, str(len(items)))
        y -= 14

        c.setFillColor(primary_color)
        c.rect(totals_x - 5, y - 16, (width - margin) - (totals_x - 5), 18, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(self.bold_font, 10)
        c.drawString(totals_x, y - 12, "Total Order Value:")
        c.drawRightString(width - margin - 5, y - 12, f"{total_amount:.2f}")
        y -= 26

        # 8. Amount in Words
        c.setFillColor(text_dark)
        words = amount_to_indian_words(Decimal(str(total_amount)))
        c.setFont(self.bold_font, 8.5)
        c.drawString(margin, y, "Amount in Words:")
        c.setFont(self.default_font, 8.5)
        c.drawString(margin + 90, y, words)
        y -= 16

        # 9. Terms and Signatory
        notes_str = data.get("notes") or branding.footer_text or "Standard procurement terms apply. Please supply items in original packing."
        c.setFont(self.default_font, 8)
        c.setFillColor(text_muted)
        c.drawString(margin, y, f"Instructions: {notes_str[:85]}")

        if branding.show_signature:
            c.setFont(self.bold_font, 9)
            c.setFillColor(primary_color)
            c.drawRightString(width - margin, y - 10, "Authorized Signatory")
            c.setStrokeColor(primary_color)
            c.line(width - margin - 120, y - 13, width - margin, y - 13)

        self._draw_footer(c, branding)
