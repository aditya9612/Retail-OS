import io
import logging
from pathlib import Path
from typing import Dict, Any, Optional

import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.core.exceptions import AppException
from app.schemas.document_setting import BrandingContext

logger = logging.getLogger(__name__)


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
        """Renders an A4 invoice PDF using ReportLab."""
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
        self._draw_document(c, data, branding, "TAX INVOICE", branding.invoice_prefix)
        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    def _render_bill(self, data: Dict[str, Any], branding: BrandingContext) -> bytes:
        """Renders a bill/receipt PDF."""
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
        self._draw_document(c, data, branding, "BILL / RECEIPT", branding.bill_prefix)
        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    def _draw_document(self, c: canvas.Canvas, data: Dict[str, Any], branding: BrandingContext, title: str, prefix: str):
        """Helper method to draw the shared structure of a document (Invoice/Bill)."""
        width, height = A4
        margin = 50
        y = height - margin

        # -- HEADER --
        # Logo
        logo_path = self._validate_logo_path(branding.logo_url)
        if logo_path:
            try:
                img = ImageReader(logo_path)
                img_w, img_h = img.getSize()
                aspect = img_w / float(img_h)
                draw_w = min(100, 50 * aspect)
                draw_h = draw_w / aspect
                c.drawImage(img, width - margin - draw_w, y - draw_h + 15, width=draw_w, height=draw_h)
            except Exception as e:
                logger.warning(f"Failed to draw logo: {str(e)}")

        # Business Details
        c.setFont(self._get_font(branding.business_name, True), 16)
        c.drawString(margin, y, branding.business_name or "")
        y -= 20

        c.setFont(self._get_font(branding.address, False), 10)
        c.drawString(margin, y, branding.address or "")
        y -= 15

        contact_info = []
        if branding.phone:
            contact_info.append(branding.phone)
        if branding.email:
            contact_info.append(branding.email)
        if contact_info:
            c.setFont(self.default_font, 9)
            c.drawString(margin, y, " | ".join(contact_info))
            y -= 15

        if branding.website:
            c.setFont(self.default_font, 9)
            c.drawString(margin, y, branding.website)
            y -= 15

        if branding.show_gstin and branding.gstin:
            c.setFont(self.default_font, 9)
            c.drawString(margin, y, f"GSTIN: {branding.gstin}")
            y -= 15

        y -= 20

        # Document Title
        c.setFont(self._get_font(title, True), 14)
        c.drawCentredString(width / 2.0, y, title)
        y -= 25

        # Document Details & QR Code
        c.setFont(self.bold_font, 10)
        invoice_num = data.get("invoice_number", "")
        doc_no = f"{prefix}-{invoice_num}" if prefix and not str(invoice_num).startswith(prefix) else str(invoice_num)
        c.drawString(margin, y, f"No: {doc_no}")

        created_at_val = data.get("created_at")
        if created_at_val:
            date_str = created_at_val.strftime("%d-%m-%Y") if hasattr(created_at_val, "strftime") else str(created_at_val)[:10]
            c.drawString(margin + 200, y, f"Date: {date_str}")

        # QR Code
        if branding.show_qr and data.get("qr_data"):
            try:
                qr = qrcode.QRCode(box_size=4, border=1)
                qr.add_data(data.get("qr_data"))
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")

                qr_buffer = io.BytesIO()
                img.save(qr_buffer, format="PNG")
                qr_buffer.seek(0)

                qr_reader = ImageReader(qr_buffer)
                c.drawImage(qr_reader, width - margin - 60, y - 40, width=60, height=60)
            except Exception as e:
                logger.warning(f"Failed to draw QR code: {str(e)}")

        y -= 25

        # Customer Details
        customer = data.get("customer", {})
        if customer:
            c.setFont(self.bold_font, 10)
            c.drawString(margin, y, "Billed To:")
            y -= 15

            cust_name = customer.get("name", "Walk-in Customer")
            c.setFont(self._get_font(cust_name, False), 10)
            c.drawString(margin, y, cust_name)
            y -= 15

            if customer.get("address"):
                c.setFont(self._get_font(customer.get("address"), False), 9)
                c.drawString(margin, y, customer.get("address"))
                y -= 15

            if customer.get("phone"):
                c.setFont(self.default_font, 9)
                c.drawString(margin, y, f"Mobile: {customer.get('phone')}")
                y -= 15

            if customer.get("gstin"):
                c.setFont(self.default_font, 9)
                c.drawString(margin, y, f"GSTIN: {customer.get('gstin')}")
                y -= 15
        else:
            c.setFont(self.default_font, 10)
            c.drawString(margin, y, "Walk-in Customer")
            y -= 15

        y -= 15

        # Helper to draw table header
        def _draw_table_header(curr_y: float) -> float:
            c.setFont(self.bold_font, 10)
            c.drawString(margin, curr_y, "Item")
            c.drawString(margin + 200, curr_y, "HSN")
            c.drawString(margin + 250, curr_y, "Qty")
            c.drawString(margin + 290, curr_y, "Price")
            c.drawString(margin + 340, curr_y, "Disc")
            c.drawString(margin + 390, curr_y, "GST")
            c.drawString(margin + 440, curr_y, "Total")
            curr_y -= 8
            c.line(margin, curr_y, width - margin, curr_y)
            curr_y -= 15
            return curr_y

        y = _draw_table_header(y)

        # -- ITEMS TABLE --
        items = data.get("items", [])
        for item in items:
            if y < 100:
                self._draw_footer(c, branding)
                c.showPage()
                y = height - margin
                y = _draw_table_header(y)

            p_name = str(item.get("product_name") or item.get("description") or "Item")
            c.setFont(self._get_font(p_name, False), 9)
            c.drawString(margin, y, p_name[:28])

            c.setFont(self.default_font, 9)
            c.drawString(margin + 200, y, str(item.get("hsn_code") or ""))
            c.drawString(margin + 250, y, str(item.get("quantity") or 1))

            unit_price = item.get("unit_price") or item.get("rate") or item.get("amount") or 0
            disc = item.get("discount_amount") or item.get("discount") or 0
            gst = item.get("gst_amount") or item.get("tax") or 0
            total = item.get("total_amount") or item.get("total") or item.get("amount") or 0

            c.drawString(margin + 290, y, f"{float(unit_price):.2f}")
            c.drawString(margin + 340, y, f"{float(disc):.2f}")
            c.drawString(margin + 390, y, f"{float(gst):.2f}")
            c.drawString(margin + 440, y, f"{float(total):.2f}")

            y -= 15

        c.line(margin, y, width - margin, y)
        y -= 15

        # -- TOTALS --
        c.setFont(self.bold_font, 10)
        totals_x = margin + 340

        subtotal_val = data.get("subtotal") if data.get("subtotal") is not None else (data.get("total") or 0)
        c.drawString(totals_x, y, "Subtotal:")
        c.drawString(totals_x + 60, y, f"{float(subtotal_val or 0):.2f}")
        y -= 15

        if data.get("discount_amount"):
            c.drawString(totals_x, y, "Discount:")
            c.drawString(totals_x + 60, y, f"-{float(data['discount_amount']):.2f}")
            y -= 15

        if data.get("cgst_amount"):
            c.drawString(totals_x, y, "CGST:")
            c.drawString(totals_x + 60, y, f"{float(data['cgst_amount']):.2f}")
            y -= 15

        if data.get("sgst_amount"):
            c.drawString(totals_x, y, "SGST:")
            c.drawString(totals_x + 60, y, f"{float(data['sgst_amount']):.2f}")
            y -= 15

        if data.get("igst_amount"):
            c.drawString(totals_x, y, "IGST:")
            c.drawString(totals_x + 60, y, f"{float(data['igst_amount']):.2f}")
            y -= 15

        grand_total = data.get("total_amount") if data.get("total_amount") is not None else (data.get("total") or 0)
        c.drawString(totals_x, y, "Grand Total:")
        c.drawString(totals_x + 60, y, f"{float(grand_total or 0):.2f}")
        y -= 25

        # -- PAYMENT DETAILS --
        if branding.show_payment_details:
            payments = data.get("payments", [])
            if payments:
                c.setFont(self.bold_font, 10)
                c.drawString(margin, y, "Payment Details:")
                y -= 15
                c.setFont(self.default_font, 9)
                for p in payments:
                    method = p.get("method") or p.get("payment_method") or "Payment"
                    amt = p.get("amount", 0)
                    ref = f" (Ref: {p['transaction_id']})" if p.get("transaction_id") else ""
                    c.drawString(margin, y, f"{str(method).upper()}: {float(amt):.2f}{ref}")
                    y -= 15

        # -- SIGNATURE --
        if branding.show_signature:
            y -= 15
            c.setFont(self.bold_font, 10)
            c.drawString(width - margin - 120, y, "Authorized Signatory")

        # Footer on the current page
        self._draw_footer(c, branding)

    def _draw_footer(self, c: canvas.Canvas, branding: BrandingContext):
        """Draws the footer text at the bottom of the page."""
        width, height = A4
        if branding.footer_text:
            c.setFont(self._get_font(branding.footer_text, False), 8)
            c.drawCentredString(width / 2.0, 30, branding.footer_text)

    def _render_credit_note(self, data: Dict[str, Any], branding: BrandingContext) -> bytes:
        """Renders an A4 credit note PDF using ReportLab."""
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
        self._draw_credit_note(c, data, branding)
        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    def _draw_credit_note(self, c: canvas.Canvas, data: Dict[str, Any], branding: BrandingContext):
        """Draws a branded GST Credit Note."""
        width, height = A4
        margin = 50
        y = height - margin

        # Logo
        logo_path = self._validate_logo_path(branding.logo_url)
        if logo_path:
            try:
                img = ImageReader(logo_path)
                img_w, img_h = img.getSize()
                aspect = img_w / float(img_h)
                draw_w = min(100, 50 * aspect)
                draw_h = draw_w / aspect
                c.drawImage(img, width - margin - draw_w, y - draw_h + 15, width=draw_w, height=draw_h)
            except Exception as e:
                logger.warning(f"Failed to draw logo: {str(e)}")

        # Business Details
        c.setFont(self._get_font(branding.business_name, True), 16)
        c.drawString(margin, y, branding.business_name or "")
        y -= 20

        c.setFont(self._get_font(branding.address, False), 10)
        c.drawString(margin, y, branding.address or "")
        y -= 15

        contact_info = []
        if branding.phone:
            contact_info.append(branding.phone)
        if branding.email:
            contact_info.append(branding.email)
        if contact_info:
            c.setFont(self.default_font, 9)
            c.drawString(margin, y, " | ".join(contact_info))
            y -= 15

        if branding.show_gstin and branding.gstin:
            c.setFont(self.default_font, 9)
            c.drawString(margin, y, f"GSTIN: {branding.gstin}")
            y -= 15

        y -= 20

        # Title
        c.setFont(self.bold_font, 14)
        c.drawCentredString(width / 2.0, y, "CREDIT NOTE")
        y -= 25

        # Document Details
        c.setFont(self.bold_font, 10)
        cn_number = data.get("credit_note_no", "")
        c.drawString(margin, y, f"Credit Note No: {cn_number}")

        created_at_val = data.get("created_at")
        if created_at_val:
            date_str = created_at_val.strftime("%d-%m-%Y") if hasattr(created_at_val, "strftime") else str(created_at_val)[:10]
            c.drawString(margin + 240, y, f"Date: {date_str}")
        y -= 20

        orig_inv = data.get("original_invoice_number")
        if orig_inv:
            c.setFont(self.default_font, 10)
            c.drawString(margin, y, f"Against Original Invoice No: {orig_inv}")
            y -= 18

        reason = data.get("reason")
        if reason:
            c.setFont(self.default_font, 10)
            c.drawString(margin, y, f"Reason for Credit Note: {reason}")
            y -= 25

        # Customer Details
        customer = data.get("customer", {})
        if customer:
            c.setFont(self.bold_font, 10)
            c.drawString(margin, y, "Issued To:")
            y -= 15
            cust_name = customer.get("name", "Customer")
            c.setFont(self._get_font(cust_name, False), 10)
            c.drawString(margin, y, cust_name)
            y -= 15
            if customer.get("phone"):
                c.setFont(self.default_font, 9)
                c.drawString(margin, y, f"Mobile: {customer.get('phone')}")
                y -= 15
            if customer.get("gstin"):
                c.setFont(self.default_font, 9)
                c.drawString(margin, y, f"GSTIN: {customer.get('gstin')}")
                y -= 15

        y -= 15

        # Credit Summary Table
        c.setFont(self.bold_font, 10)
        c.drawString(margin, y, "Description")
        c.drawString(margin + 340, y, "Amount (INR)")
        y -= 8
        c.line(margin, y, width - margin, y)
        y -= 18

        c.setFont(self.default_font, 10)
        c.drawString(margin, y, "Refund / Returned Value")
        refund_amount = float(data.get("refund_amount", 0))
        c.drawString(margin + 340, y, f"{refund_amount:.2f}")
        y -= 16

        if data.get("cgst_amount"):
            c.drawString(margin, y, "CGST Credit Adjustment")
            c.drawString(margin + 340, y, f"{float(data['cgst_amount']):.2f}")
            y -= 16

        if data.get("sgst_amount"):
            c.drawString(margin, y, "SGST Credit Adjustment")
            c.drawString(margin + 340, y, f"{float(data['sgst_amount']):.2f}")
            y -= 16

        if data.get("igst_amount"):
            c.drawString(margin, y, "IGST Credit Adjustment")
            c.drawString(margin + 340, y, f"{float(data['igst_amount']):.2f}")
            y -= 16

        c.line(margin, y, width - margin, y)
        y -= 18

        c.setFont(self.bold_font, 11)
        c.drawString(margin, y, "Total Credited Amount:")
        c.drawString(margin + 340, y, f"{refund_amount:.2f}")
        y -= 40

        # Signatory
        c.setFont(self.bold_font, 10)
        c.drawString(width - margin - 140, y, "Authorized Signatory")
        y -= 10
        c.line(width - margin - 150, y, width - margin, y)

        self._draw_footer(c, branding)

    def _render_purchase_order(self, data: Dict[str, Any], branding: BrandingContext) -> bytes:
        """Renders an A4 purchase order PDF using ReportLab."""
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
        self._draw_purchase_order(c, data, branding)
        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    def _draw_purchase_order(self, c: canvas.Canvas, data: Dict[str, Any], branding: BrandingContext):
        """Draws a branded Purchase Order for vendors."""
        width, height = A4
        margin = 50
        y = height - margin

        # Logo
        logo_path = self._validate_logo_path(branding.logo_url)
        if logo_path:
            try:
                img = ImageReader(logo_path)
                img_w, img_h = img.getSize()
                aspect = img_w / float(img_h)
                draw_w = min(100, 50 * aspect)
                draw_h = draw_w / aspect
                c.drawImage(img, width - margin - draw_w, y - draw_h + 15, width=draw_w, height=draw_h)
            except Exception as e:
                logger.warning(f"Failed to draw logo: {str(e)}")

        # Business Details
        c.setFont(self._get_font(branding.business_name, True), 16)
        c.drawString(margin, y, branding.business_name or "")
        y -= 20

        c.setFont(self._get_font(branding.address, False), 10)
        c.drawString(margin, y, branding.address or "")
        y -= 15

        contact_info = []
        if branding.phone:
            contact_info.append(branding.phone)
        if branding.email:
            contact_info.append(branding.email)
        if contact_info:
            c.setFont(self.default_font, 9)
            c.drawString(margin, y, " | ".join(contact_info))
            y -= 15

        if branding.show_gstin and branding.gstin:
            c.setFont(self.default_font, 9)
            c.drawString(margin, y, f"GSTIN: {branding.gstin}")
            y -= 15

        y -= 20

        # Title
        c.setFont(self.bold_font, 14)
        c.drawCentredString(width / 2.0, y, "PURCHASE ORDER")
        y -= 25

        # Document Details
        c.setFont(self.bold_font, 10)
        po_number = data.get("order_number") or data.get("po_number", "")
        c.drawString(margin, y, f"PO Number: {po_number}")

        order_date_val = data.get("order_date") or data.get("created_at")
        if order_date_val:
            date_str = order_date_val.strftime("%d-%m-%Y") if hasattr(order_date_val, "strftime") else str(order_date_val)[:10]
            c.drawString(margin + 240, y, f"Date: {date_str}")
        y -= 20

        # Supplier Info
        supplier = data.get("supplier", {})
        c.setFont(self.bold_font, 10)
        c.drawString(margin, y, "Vendor / Supplier:")
        y -= 15

        supp_name = supplier.get("name", "Vendor")
        c.setFont(self._get_font(supp_name, False), 10)
        c.drawString(margin, y, supp_name)
        y -= 15

        if supplier.get("address"):
            c.setFont(self._get_font(supplier.get("address"), False), 9)
            c.drawString(margin, y, supplier.get("address"))
            y -= 15

        if supplier.get("phone") or supplier.get("email"):
            s_contact = " | ".join(filter(None, [supplier.get("phone"), supplier.get("email")]))
            c.setFont(self.default_font, 9)
            c.drawString(margin, y, s_contact)
            y -= 15

        if supplier.get("gstin"):
            c.setFont(self.default_font, 9)
            c.drawString(margin, y, f"GSTIN: {supplier.get('gstin')}")
            y -= 15

        y -= 15

        # Items Table Header
        c.setFont(self.bold_font, 10)
        c.drawString(margin, y, "Item Description")
        c.drawString(margin + 230, y, "SKU")
        c.drawString(margin + 330, y, "Qty")
        c.drawString(margin + 380, y, "Unit Cost")
        c.drawString(margin + 440, y, "Total")
        y -= 8
        c.line(margin, y, width - margin, y)
        y -= 15

        # Items Table Rows
        items = data.get("items", [])
        for it in items:
            if y < 100:
                self._draw_footer(c, branding)
                c.showPage()
                y = height - margin - 20

            it_name = str(it.get("product_name") or it.get("name") or "Product")
            c.setFont(self._get_font(it_name, False), 9)
            c.drawString(margin, y, it_name[:32])

            c.setFont(self.default_font, 9)
            c.drawString(margin + 230, y, str(it.get("sku") or ""))
            qty = it.get("quantity") or 0
            c.drawString(margin + 330, y, str(qty))

            uc = float(it.get("unit_cost") or 0)
            c.drawString(margin + 380, y, f"{uc:.2f}")

            line_tot = float(it.get("total_cost") or (qty * uc))
            c.drawString(margin + 440, y, f"{line_tot:.2f}")
            y -= 15

        c.line(margin, y, width - margin, y)
        y -= 18

        # Total PO Amount
        total_amount = float(data.get("total_amount") or 0)
        c.setFont(self.bold_font, 11)
        c.drawString(margin + 330, y, "Total Order Value:")
        c.drawString(margin + 440, y, f"{total_amount:.2f}")
        y -= 35

        # Authorized Signatory
        c.setFont(self.bold_font, 10)
        c.drawString(width - margin - 140, y, "Authorized Signatory")
        y -= 10
        c.line(width - margin - 150, y, width - margin, y)

        self._draw_footer(c, branding)
