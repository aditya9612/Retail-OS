import base64
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.product import Product
from app.models.whatsapp import KhataFollowup, WhatsAppSetting
from app.services.whatsapp_service import WhatsAppService

client = TestClient(app)


@pytest.fixture
def wa_ai_setup(unique_slug):
    email = f"wa-ai-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "WhatsApp AI Mart",
            "slug": unique_slug,
            "email": email,
            "admin_name": "AI Admin",
            "password": "testpass123",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "testpass123"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    store = client.post(
        "/api/v1/stores",
        json={"name": "Shivaji Supermarket", "code": "SSM1", "phone": "9876543210"},
        headers=headers,
    ).json()

    # Create common grocery products
    p1 = client.post(
        "/api/v1/products",
        json={
            "name": "दावत बासमती तांदूळ",
            "sku": "RICE-001",
            "price": "120.00",
            "gst_rate": "0.00",
            "hsn_code": "1006",
            "unit": "kg",
        },
        headers=headers,
    ).json()

    p2 = client.post(
        "/api/v1/products",
        json={
            "name": "फॉर्च्युन सूर्यफूल तेल",
            "sku": "OIL-001",
            "price": "180.00",
            "gst_rate": "5.00",
            "hsn_code": "1512",
            "unit": "l",
        },
        headers=headers,
    ).json()

    p3 = client.post(
        "/api/v1/products",
        json={
            "name": "माधुर शुद्ध साखर",
            "sku": "SUG-001",
            "price": "50.00",
            "gst_rate": "0.00",
            "hsn_code": "1701",
            "unit": "kg",
        },
        headers=headers,
    ).json()

    return {
        "headers": headers,
        "store": store,
        "products": [p1, p2, p3],
    }


# ==============================================================================
# 1. TEST FEATURE 1: HANDWRITTEN GROCERY LIST OCR (चिठ्ठी स्कॅनर)
# ==============================================================================

def test_handwritten_grocery_ocr_and_order_creation(wa_ai_setup):
    headers = wa_ai_setup["headers"]
    store_id = wa_ai_setup["store"]["id"]

    # Sample base64 image data (mock grocery chit)
    sample_chit_b64 = base64.b64encode(b"HANDWRITTEN_GROCERY_SLIP_SAKHAR_TEL_RICE").decode("ascii")

    # Mock WhatsAppService.send_message to prevent actual network calls
    with patch.object(WhatsAppService, "send_message", return_value={"status": "success", "message_id": "wamid.OCR123"}):
        resp = client.post(
            "/api/v1/whatsapp/ocr-grocery-list",
            json={
                "image_base64": sample_chit_b64,
                "mime_type": "image/jpeg",
                "recipient_phone": "9876599991",
                "sender_name": "सुनील शिंदे",
                "auto_create_order": True,
                "store_id": store_id,
            },
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "success"
        assert len(data["extracted_items"]) >= 1
        assert len(data["matched_items"]) >= 1
        assert data["order_id"] is not None
        assert data["order_number"].startswith("ORD-OCR-")
        assert data["total_amount"] > 0
        assert "upi://pay" in data["upi_payment_link"]
        assert "किराणा चिठ्ठी स्कॅन यशस्वी" in data["reply_message"]


def test_handwritten_grocery_ocr_upload_file(wa_ai_setup):
    headers = wa_ai_setup["headers"]
    fake_image_bytes = b"MOCK_JPEG_IMAGE_CHIT_DATA"

    with patch.object(WhatsAppService, "send_message", return_value={"status": "success", "message_id": "wamid.OCRFILE"}):
        resp = client.post(
            "/api/v1/whatsapp/ocr-grocery-list/upload",
            files={"file": ("chit.jpg", fake_image_bytes, "image/jpeg")},
            params={"recipient_phone": "9876599992", "auto_create_order": "true"},
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert len(data["extracted_items"]) >= 1
        assert data["total_amount"] > 0


# ==============================================================================
# 2. TEST FEATURE 2: 24/7 CONVERSATIONAL ORDERING BOT
# ==============================================================================

def test_conversational_order_marathi_fractions(wa_ai_setup):
    headers = wa_ai_setup["headers"]

    # Natural conversation with Marathi fractional quantities:
    # "२ किलो बासमती तांदूळ, १ लिटर फॉर्च्युन तेल आणि अर्धा किलो साखर घरी पाठवा"
    order_text = "२ किलो बासमती तांदूळ, १ लिटर फॉर्च्युन तेल आणि अर्धा किलो साखर घरी पाठवा"

    with patch.object(WhatsAppService, "send_message", return_value={"status": "success", "message_id": "wamid.CHATORD1"}):
        resp = client.post(
            "/api/v1/whatsapp/conversational-order",
            json={
                "phone": "9876599993",
                "message": order_text,
                "sender_name": "विकास माने",
            },
            headers=headers,
        )

        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "success"
        assert data["intent"] == "order_created"
        assert data["order_id"] is not None
        assert data["order_number"].startswith("ORD-WA-")
        # Subtotal calculation:
        # 2 kg Rice @ 120 = 240
        # 1 L Oil @ 180 + 5% tax (9) = 189
        # 0.5 kg Sugar @ 50 = 25
        # Total approx 454
        assert data["total_amount"] > 400
        assert "upi://pay" in data["upi_link"]
        assert "ऑर्डर तयार झाली" in data["reply"]


def test_conversational_greeting_and_help(wa_ai_setup):
    headers = wa_ai_setup["headers"]

    with patch.object(WhatsAppService, "send_message", return_value={"status": "success"}):
        # Greeting
        resp = client.post(
            "/api/v1/whatsapp/conversational-order",
            json={"phone": "9876599994", "message": "नमस्कार"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["intent"] == "greeting"
        assert "स्वागत आहे" in resp.json()["reply"]

        # Unknown / Help prompt
        resp2 = client.post(
            "/api/v1/whatsapp/conversational-order",
            json={"phone": "9876599994", "message": "काय चालू आहे?"},
            headers=headers,
        )
        assert resp2.status_code == 200
        assert "समजले नाही" in resp2.json()["reply"]


# ==============================================================================
# 3. TEST FEATURE 3: SMART KHATA (उधारी) RECOVERY AI AGENT
# ==============================================================================

def test_smart_khata_full_lifecycle(wa_ai_setup):
    headers = wa_ai_setup["headers"]
    tenant_id = wa_ai_setup["store"]["tenant_id"]
    db = SessionLocal()

    try:
        # Create an overdue Khata customer
        customer = Customer(
            tenant_id=tenant_id,
            name="दिनेश पवार",
            phone="9876599995",
            outstanding_balance=Decimal("3500.00"),
            credit_limit=Decimal("5000.00"),
            whatsapp_opt_in=True,
            status="active",
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)
        cust_id = customer.id

        # Step 1: Query pending Khata customers
        pending_resp = client.get("/api/v1/whatsapp/khata/pending", headers=headers)
        assert pending_resp.status_code == 200
        pending_items = pending_resp.json()
        assert len(pending_items) >= 1
        matched_cust = next((c for c in pending_items if c["customer_id"] == cust_id), None)
        assert matched_cust is not None
        assert matched_cust["outstanding_balance"] == 3500.0
        assert matched_cust["recovery_status"] == "pending"

        # Step 2: Send smart reminder
        with patch.object(WhatsAppService, "send_message", return_value={"status": "success", "message_id": "wamid.KHATA001"}):
            rem_resp = client.post(
                f"/api/v1/whatsapp/khata/send-reminder/{cust_id}",
                json={"custom_note": "कृपया वेळेवर भरणा करावा."},
                headers=headers,
            )
            assert rem_resp.status_code == 200
            rem_data = rem_resp.json()
            assert rem_data["status"] == "success"
            assert rem_data["outstanding_amount"] == 3500.0
            assert "upi://pay" in rem_data["upi_link"]

        # Step 3: Verify KhataFollowup entry in DB
        followup = (
            db.query(KhataFollowup)
            .filter(KhataFollowup.customer_id == cust_id)
            .order_by(KhataFollowup.id.desc())
            .first()
        )
        assert followup is not None
        assert followup.status == "reminder_sent"
        assert followup.outstanding_amount == Decimal("3500.00")

        # Step 4: Process Customer Reply: Promise to Pay ("मी उद्या पैसे देतो")
        with patch.object(WhatsAppService, "send_message", return_value={"status": "success"}):
            reply_resp = client.post(
                "/api/v1/whatsapp/khata/process-reply",
                json={
                    "customer_id": cust_id,
                    "reply_message": "मी उद्या संध्याकाळी ५ वाजता देतो",
                },
                headers=headers,
            )
            assert reply_resp.status_code == 200
            rep_data = reply_resp.json()
            assert rep_data["status"] == "success"
            assert rep_data["detected_intent"] == "promise_to_pay"
            assert rep_data["followup_status"] == "promised"
            assert rep_data["promised_date"] is not None
            assert "उद्या" in rep_data["acknowledgment_reply"] or "धन्यवाद" in rep_data["acknowledgment_reply"]

            db.refresh(followup)
            assert followup.status == "promised"
            assert followup.detected_intent == "promise_to_pay"

        # Step 5: Process Customer Reply: Already Paid ("Google Pay केले आहे")
        with patch.object(WhatsAppService, "send_message", return_value={"status": "success"}):
            reply_resp2 = client.post(
                "/api/v1/whatsapp/khata/process-reply",
                json={
                    "customer_id": cust_id,
                    "reply_message": "मी गुगल पे द्वारे पैसे पाठवले आहेत चेक करा",
                },
                headers=headers,
            )
            assert reply_resp2.status_code == 200
            rep2_data = reply_resp2.json()
            assert rep2_data["detected_intent"] == "already_paid"
            assert rep2_data["followup_status"] == "paid"

        # Step 6: List Followups history
        f_resp = client.get("/api/v1/whatsapp/khata/followups", headers=headers)
        assert f_resp.status_code == 200
        assert f_resp.json()["total"] >= 1

    finally:
        db.close()
