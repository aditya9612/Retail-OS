import os
import sys
import re
from pathlib import Path
import pytest

from app.services.document_renderer_service import DocumentRenderer, RendererError
from app.schemas.document_setting import BrandingContext
from app.services.document_settings_service import DocumentSettingsService
from app.models.tenant import Tenant
from app.models.store import Store
from app.models.document_setting import DocumentSetting
from app.schemas.document_setting import DocumentSettingCreate, DocumentSettingUpdate


def parse_pdf_structure(pdf_bytes: bytes) -> dict:
    assert pdf_bytes.startswith(b"%PDF-"), "Missing %PDF header"
    assert b"%%EOF" in pdf_bytes, "Missing %%EOF marker"
    assert b"/Catalog" in pdf_bytes, "Missing /Catalog dictionary"
    assert b"/Pages" in pdf_bytes, "Missing /Pages dictionary"
    assert b"xref" in pdf_bytes, "Missing xref table"

    page_count = len(re.findall(rb"/Type\s*/Page\b", pdf_bytes))

    # Extract uncompressed text literals
    text_literals = []
    for m in re.finditer(rb"\((.*?)\)\s*Tj", pdf_bytes):
        raw = m.group(1).replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
        text_literals.append(raw.decode("latin1", errors="ignore"))

    fonts = [m.group(1).decode("latin1") for m in re.finditer(rb"/BaseFont\s*/([^\s/>]+)", pdf_bytes)]

    return {
        "page_count": page_count,
        "fonts": fonts,
        "text": " ".join(text_literals),
    }


@pytest.fixture
def sample_branding():
    return BrandingContext(
        business_name="Test MegaMart",
        address="123 Test St, Mumbai",
        phone="+91 9876543210",
        email="test@example.com",
        website="https://example.com",
        gstin="27AAAAA0000A1Z5",
        footer_text="Test Footer Note",
        invoice_prefix="INV",
        bill_prefix="BILL",
        show_gstin=True,
        show_qr=True,
        show_signature=True,
        show_payment_details=True,
        logo_url=None,
    )


@pytest.fixture
def sample_invoice_data():
    return {
        "invoice_number": "1001",
        "created_at": "2026-10-04",
        "qr_data": "INVOICE:1001|GSTIN:27AAAAA0000A1Z5|TOTAL:354.00",
        "customer": {
            "name": "John Doe",
            "phone": "9999999999",
            "address": "456 Customer Ave",
            "gstin": "27BBBBB1111B1Z2",
        },
        "items": [
            {"product_name": "Product Alpha", "hsn_code": "1001", "quantity": 1, "unit_price": 100.0, "discount_amount": 0.0, "gst_amount": 18.0, "total_amount": 118.0},
            {"product_name": "Product Beta", "hsn_code": "1002", "quantity": 2, "unit_price": 100.0, "discount_amount": 0.0, "gst_amount": 36.0, "total_amount": 236.0},
        ],
        "subtotal": 300.0,
        "discount_amount": 0.0,
        "cgst_amount": 27.0,
        "sgst_amount": 27.0,
        "igst_amount": 0.0,
        "total_amount": 354.0,
        "payments": [
            {"method": "cash", "amount": 200.0},
            {"method": "upi", "amount": 154.0, "transaction_id": "TXN123"},
        ],
    }


# 1. Renderer success
def test_renderer_generates_valid_pdf(sample_branding, sample_invoice_data):
    renderer = DocumentRenderer()
    pdf_bytes = renderer.render("invoice", sample_invoice_data, sample_branding)
    parsed = parse_pdf_structure(pdf_bytes)
    assert parsed["page_count"] == 1
    assert "TAX INVOICE" in parsed["text"]
    assert "Test MegaMart" in parsed["text"]
    assert "Product Alpha" in parsed["text"]
    assert "354.00" in parsed["text"]


# 2. Template name compatibility (.html suffix)
def test_renderer_template_name_html_alias(sample_branding, sample_invoice_data):
    renderer = DocumentRenderer()
    pdf_bytes = renderer.render("invoice.html", sample_invoice_data, sample_branding)
    assert pdf_bytes.startswith(b"%PDF-")
    assert b"%%EOF" in pdf_bytes


# 3. Missing / invalid template failure
def test_renderer_unknown_template_raises_error(sample_branding, sample_invoice_data):
    renderer = DocumentRenderer()
    with pytest.raises(RendererError) as exc_info:
        renderer.render("non_existent_template", sample_invoice_data, sample_branding)
    assert "Unsupported template type" in str(exc_info.value)


# 4. Bill PDF rendering
def test_renderer_bill_rendering(sample_branding, sample_invoice_data):
    renderer = DocumentRenderer()
    pdf_bytes = renderer.render("bill", sample_invoice_data, sample_branding)
    parsed = parse_pdf_structure(pdf_bytes)
    assert parsed["page_count"] == 1
    assert "BILL / RECEIPT" in parsed["text"]
    assert "BILL-1001" in parsed["text"]


# 5. GSTIN flag verification
def test_gstin_flag_control(sample_branding, sample_invoice_data):
    renderer = DocumentRenderer()
    # Enabled
    pdf_enabled = renderer.render("invoice", sample_invoice_data, sample_branding)
    assert b"27AAAAA0000A1Z5" in pdf_enabled

    # Disabled
    disabled_branding = sample_branding.model_copy(update={"show_gstin": False})
    pdf_disabled = renderer.render("invoice", sample_invoice_data, disabled_branding)
    assert b"27AAAAA0000A1Z5" not in pdf_disabled


# 6. QR flag verification
def test_qr_flag_control(sample_branding, sample_invoice_data):
    renderer = DocumentRenderer()
    # Enabled
    pdf_qr = renderer.render("invoice", sample_invoice_data, sample_branding)
    # Disabled
    disabled_branding = sample_branding.model_copy(update={"show_qr": False})
    pdf_no_qr = renderer.render("invoice", sample_invoice_data, disabled_branding)
    # QR draws image stream, so disabled PDF should be smaller
    assert len(pdf_qr) > len(pdf_no_qr)


# 7. Signature flag verification
def test_signature_flag_control(sample_branding, sample_invoice_data):
    renderer = DocumentRenderer()
    pdf_sig = renderer.render("invoice", sample_invoice_data, sample_branding)
    assert b"Authorized Signatory" in pdf_sig

    no_sig_branding = sample_branding.model_copy(update={"show_signature": False})
    pdf_no_sig = renderer.render("invoice", sample_invoice_data, no_sig_branding)
    assert b"Authorized Signatory" not in pdf_no_sig


# 8. Payment details flag verification
def test_payment_details_flag_control(sample_branding, sample_invoice_data):
    renderer = DocumentRenderer()
    pdf_pay = renderer.render("invoice", sample_invoice_data, sample_branding)
    assert b"Payment Details:" in pdf_pay
    assert b"CASH: 200.00" in pdf_pay

    no_pay_branding = sample_branding.model_copy(update={"show_payment_details": False})
    pdf_no_pay = renderer.render("invoice", sample_invoice_data, no_pay_branding)
    assert b"Payment Details:" not in pdf_no_pay


# 9. Footer verification
def test_footer_text_rendering(sample_branding, sample_invoice_data):
    renderer = DocumentRenderer()
    pdf_bytes = renderer.render("invoice", sample_invoice_data, sample_branding)
    assert b"Test Footer Note" in pdf_bytes


# 10. Logo security - valid and invalid paths
def test_logo_security_and_validation():
    renderer = DocumentRenderer()

    # Reject path traversal
    assert renderer._validate_logo_path("../../etc/passwd") is None
    assert renderer._validate_logo_path("uploads/../secret.png") is None

    # Reject unsupported extensions
    assert renderer._validate_logo_path("uploads/logo.svg") is None
    assert renderer._validate_logo_path("uploads/logo.exe") is None
    assert renderer._validate_logo_path("uploads/logo.pdf") is None

    # Reject external URLs
    assert renderer._validate_logo_path("http://evil.com/logo.png") is None
    assert renderer._validate_logo_path("https://evil.com/logo.jpg") is None

    # Reject non-existent file
    assert renderer._validate_logo_path("uploads/does_not_exist_xyz.png") is None

    # Accept valid image within uploads directory
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(exist_ok=True)
    test_logo = uploads_dir / "test_logo.png"
    # Create minimal 1x1 png image
    test_logo.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    validated = renderer._validate_logo_path("uploads/test_logo.png")
    assert validated is not None
    assert validated.endswith("test_logo.png")


# 11. Unicode and Marathi rendering
def test_unicode_marathi_rendering():
    renderer = DocumentRenderer()
    marathi_branding = BrandingContext(
        business_name="श्री गणेश ट्रेडर्स",
        address="पुणे, महाराष्ट्र",
        footer_text="गौरव ट्रेडर्स - धन्यवाद!",
        invoice_prefix="बिल",
    )
    data = {
        "invoice_number": "१०१",
        "customer": {"name": "राहुल जोशी"},
        "items": [{"product_name": "बासमती तांदूळ", "quantity": 1, "unit_price": 500, "total_amount": 500}],
        "total": 500,
    }
    pdf_bytes = renderer.render("invoice", data, marathi_branding)
    assert pdf_bytes.startswith(b"%PDF-")
    assert b"%%EOF" in pdf_bytes
    # Verify embedded Devanagari font and ToUnicode CMap
    assert b"/ToUnicode" in pdf_bytes
    assert any(b"Mangal" in pdf_bytes or b"Devanagari" in pdf_bytes for _ in [1])


# 12. Multi-page document pagination
def test_multipage_invoice_rendering(sample_branding):
    renderer = DocumentRenderer()
    items = [
        {"product_name": f"Item SKU {i}", "quantity": i, "unit_price": 100.0, "total_amount": 100.0 * i}
        for i in range(1, 35)
    ]
    data = {
        "invoice_number": "MULTI-01",
        "items": items,
        "total": sum(it["total_amount"] for it in items),
    }
    pdf_bytes = renderer.render("invoice", data, sample_branding)
    parsed = parse_pdf_structure(pdf_bytes)
    assert parsed["page_count"] == 2
    assert "MULTI-01" in parsed["text"]


# 13. Tenant and Store isolation with BrandingContext resolution
def test_tenant_and_store_isolation_integration(db_session=None):
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        t_a = db.query(Tenant).filter(Tenant.domain == "unit-iso-a.test").first()
        if not t_a:
            t_a = Tenant(name="Alpha Entity", domain="unit-iso-a.test", plan="pro")
            db.add(t_a)
            db.commit()
            db.refresh(t_a)

        t_b = db.query(Tenant).filter(Tenant.domain == "unit-iso-b.test").first()
        if not t_b:
            t_b = Tenant(name="Beta Entity", domain="unit-iso-b.test", plan="pro")
            db.add(t_b)
            db.commit()
            db.refresh(t_b)

        s_a = db.query(Store).filter(Store.tenant_id == t_a.id, Store.name == "Store A1").first()
        if not s_a:
            s_a = Store(tenant_id=t_a.id, name="Store A1", code="SA1")
            db.add(s_a)
            db.commit()
            db.refresh(s_a)

        s_b = db.query(Store).filter(Store.tenant_id == t_b.id, Store.name == "Store B1").first()
        if not s_b:
            s_b = Store(tenant_id=t_b.id, name="Store B1", code="SB1")
            db.add(s_b)
            db.commit()
            db.refresh(s_b)

        service = DocumentSettingsService(db)
        renderer = DocumentRenderer()

        # Set tenant brandings
        service.create_or_update_setting(t_a.id, DocumentSettingCreate(business_name="Alpha Brand Name"))
        service.create_or_update_setting(t_b.id, DocumentSettingCreate(business_name="Beta Brand Name"))

        brand_a = service.resolve_branding(t_a.id, s_a.id)
        brand_b = service.resolve_branding(t_b.id, s_b.id)

        pdf_a = renderer.render("invoice", {"invoice_number": "1"}, brand_a)
        pdf_b = renderer.render("invoice", {"invoice_number": "2"}, brand_b)

        # Tenant isolation
        assert b"Alpha Brand Name" in pdf_a
        assert b"Beta Brand Name" not in pdf_a
        assert b"Beta Brand Name" in pdf_b
        assert b"Alpha Brand Name" not in pdf_b

        # Store override
        service.create_or_update_setting(t_a.id, DocumentSettingUpdate(business_name="Store A1 Custom Override"), store_id=s_a.id)
        brand_s_a = service.resolve_branding(t_a.id, s_a.id)
        pdf_s_a = renderer.render("invoice", {"invoice_number": "3"}, brand_s_a)
        assert b"Store A1 Custom Override" in pdf_s_a
        assert b"Alpha Brand Name" not in pdf_s_a

        # Store override NULL fallback
        service.create_or_update_setting(t_a.id, DocumentSettingUpdate(business_name=None), store_id=s_a.id)
        brand_fallback = service.resolve_branding(t_a.id, s_a.id)
        pdf_fallback = renderer.render("invoice", {"invoice_number": "4"}, brand_fallback)
        assert b"Alpha Brand Name" in pdf_fallback
