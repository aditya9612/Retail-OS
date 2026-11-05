import io
from decimal import Decimal
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.category import Category
from app.models.product import Product
from app.models.store import Store
from app.services.voice_pos_service import VoicePOSService, normalize_voice_digits

client = TestClient(app)


# ==============================================================================
# 1. UNIT TESTS: Extraction & Digit Normalization
# ==============================================================================

def test_voice_digit_normalization():
    assert normalize_voice_digits("२ किलो तांदूळ, रोख ५००") == "2 किलो तांदूळ, रोख 500"
    assert normalize_voice_digits("०१२३४५६७८९") == "0123456789"
    assert normalize_voice_digits("1 kg sugar") == "1 kg sugar"


def test_voice_tender_extraction():
    service = VoicePOSService(None)

    # Marathi cash pattern: 'रोख ५००'
    t1, rest1 = service.extract_tender_info("२ किलो बासमती तांदूळ, १ लिटर फॉर्च्युन तेल, रोख ५००")
    assert t1 is not None
    assert t1["payment_mode"] == "cash"
    assert t1["tendered_amount"] == Decimal("500")
    assert "रोख" not in rest1
    assert "500" not in rest1

    # English cash pattern: 'cash 1000'
    t2, rest2 = service.extract_tender_info("2 kg basmati rice, cash 1000")
    assert t2 is not None
    assert t2["payment_mode"] == "cash"
    assert t2["tendered_amount"] == Decimal("1000")

    # Inverted cash pattern: '500 रोख'
    t3, rest3 = service.extract_tender_info("1 तेल, 500 रोख")
    assert t3 is not None
    assert t3["tendered_amount"] == Decimal("500")

    # UPI / Online pattern
    t4, rest4 = service.extract_tender_info("1 bread, online 150")
    assert t4 is not None
    assert t4["payment_mode"] == "upi"
    assert t4["tendered_amount"] == Decimal("150")

    # No tender mentioned
    t5, rest5 = service.extract_tender_info("२ किलो साखर, १ ब्रेड")
    assert t5 is None
    assert "साखर" in rest5


def test_voice_item_phrase_extraction():
    service = VoicePOSService(None)
    items = service.extract_voice_items("२ किलो बासमती तांदूळ, १ लिटर फॉर्च्युन तेल")
    assert len(items) == 2
    assert items[0]["quantity"] == 2
    assert items[0]["unit"] == "kg"
    assert "बासमती" in items[0]["item_name"]

    assert items[1]["quantity"] == 1
    assert items[1]["unit"] == "l"
    assert "फॉर्च्युन" in items[1]["item_name"]


# ==============================================================================
# 2. INTEGRATION TESTS: Voice Command POS Billing & Audio API
# ==============================================================================

@pytest.fixture
def voice_billing_setup(unique_slug):
    email = f"voice-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "Voice Retail Hypermarket",
            "slug": unique_slug,
            "email": email,
            "admin_name": "Cashier Voice Admin",
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
        json={"name": "Shivaji Voice Express", "code": "SVE-01"},
        headers=headers,
    ).json()

    tenant_id = store["tenant_id"]
    store_id = store["id"]

    db = SessionLocal()
    try:
        cat_grocery = Category(tenant_id=tenant_id, name="Groceries", is_active=True)
        cat_personal = Category(tenant_id=tenant_id, name="Personal Care", is_active=True)
        db.add_all([cat_grocery, cat_personal])
        db.flush()

        p_rice = Product(
            tenant_id=tenant_id,
            category_id=cat_grocery.id,
            name="Daawat Basmati Rice 1kg",
            sku="RICE-001",
            selling_price=Decimal("120.00"),
            cost_price=Decimal("95.00"),
            unit="kg",
            is_active=True,
        )
        p_oil = Product(
            tenant_id=tenant_id,
            category_id=cat_grocery.id,
            name="Fortune Sunlite Refined Oil 1L",
            brand="Fortune",
            sku="OIL-001",
            selling_price=Decimal("140.00"),
            cost_price=Decimal("115.00"),
            unit="ltr",
            is_active=True,
        )
        p_soap = Product(
            tenant_id=tenant_id,
            category_id=cat_personal.id,
            name="Dettol Original Soap",
            brand="Dettol",
            sku="SOAP-001",
            selling_price=Decimal("40.00"),
            cost_price=Decimal("30.00"),
            unit="pcs",
            is_active=True,
        )
        db.add_all([p_rice, p_oil, p_soap])
        db.commit()

        return {
            "headers": headers,
            "tenant_id": tenant_id,
            "store_id": store_id,
            "p_rice_id": p_rice.id,
            "p_oil_id": p_oil.id,
            "p_soap_id": p_soap.id,
        }
    finally:
        db.close()


def test_voice_command_billing_marathi(voice_billing_setup):
    headers = voice_billing_setup["headers"]
    store_id = voice_billing_setup["store_id"]

    # Cashier speaks: "२ किलो बासमती तांदूळ, १ लिटर फॉर्च्युन तेल, रोख ५००."
    command = "२ किलो बासमती तांदूळ, १ लिटर फॉर्च्युन तेल, रोख ५००."

    resp = client.post(
        "/api/v1/billing/voice-command",
        json={
            "command": command,
            "store_id": store_id,
            "language": "mr",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["recognized_command"] == command
    # 2 items added: Basmati Rice (120 * 2 = 240) + Fortune Oil (140 * 1 = 140) = 380.00
    assert len(data["items_added"]) == 2
    assert any("Basmati" in it["product_name"] and float(it["quantity"]) == 2 for it in data["items_added"])
    assert any("Fortune" in it["product_name"] and float(it["quantity"]) == 1 for it in data["items_added"])

    # Verify Tender & Change Due: 500 cash tendered, 380 total, 120 change due
    assert data["tender"] is not None
    assert data["tender"]["payment_mode"] == "cash"
    assert float(data["tender"]["tendered_amount"]) == 500.00
    assert float(data["tender"]["grand_total"]) == 380.00
    assert float(data["tender"]["change_due"]) == 120.00

    # Verify Cart State
    assert float(data["cart"]["grand_total"]) == 380.00
    assert len(data["cart"]["items"]) == 2

    # Verify Natural Voice Feedback in Marathi
    feedback = data["voice_feedback"]
    assert "वस्तू कार्टमध्ये जोडल्या" in feedback
    assert "रोख ₹500.00 पैकी ₹120.00 परत द्या" in feedback or "परत द्या" in feedback


def test_voice_command_billing_english_and_single_item(voice_billing_setup):
    headers = voice_billing_setup["headers"]
    store_id = voice_billing_setup["store_id"]

    # Cashier speaks: "5 soap, cash 250"
    command = "5 soap, cash 250"

    resp = client.post(
        "/api/v1/billing/voice-command",
        json={
            "command": command,
            "store_id": store_id,
            "language": "en",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # Soap (40 * 5 = 200)
    assert len(data["items_added"]) >= 1
    assert any("Soap" in it["product_name"] for it in data["items_added"])
    assert float(data["tender"]["tendered_amount"]) == 250.00
    assert float(data["tender"]["change_due"]) >= 50.00
    assert "Return" in data["voice_feedback"] or "Cash" in data["voice_feedback"]


def test_voice_command_audio_file_upload(voice_billing_setup):
    headers = voice_billing_setup["headers"]
    store_id = voice_billing_setup["store_id"]

    # Mock audio bytes (e.g. from browser mic)
    fake_audio_bytes = b"RIFF....WAVEfmt ....data...."

    # Mock Speech-to-Text transcription
    with patch.object(
        VoicePOSService,
        "transcribe_audio_bytes",
        return_value="२ किलो बासमती तांदूळ, रोख ५००",
    ):
        files = {
            "file": ("mic_recording.webm", io.BytesIO(fake_audio_bytes), "audio/webm"),
        }
        data = {
            "store_id": str(store_id),
            "language": "mr",
        }
        resp = client.post(
            "/api/v1/billing/voice-command/audio",
            files=files,
            data=data,
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        res_data = resp.json()
        assert res_data["recognized_command"] == "२ किलो बासमती तांदूळ, रोख ५००"
        assert len(res_data["items_added"]) >= 1
        assert "Basmati" in res_data["items_added"][0]["product_name"]
        assert float(res_data["tender"]["tendered_amount"]) == 500.00
