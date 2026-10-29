from decimal import Decimal
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.whatsapp import WhatsAppSetting, WhatsAppLog
from app.services.whatsapp_service import normalize_whatsapp_phone, WhatsAppService

client = TestClient(app)


# ------------------------------------------------------------------------------
# 1. Unit Tests: Phone Number Normalization & Payload Formatting
# ------------------------------------------------------------------------------

def test_normalize_whatsapp_phone():
    # 10-digit Indian numbers should get '91' prefix
    assert normalize_whatsapp_phone("9876543210") == "919876543210"
    # Numbers with leading 0
    assert normalize_whatsapp_phone("09876543210") == "919876543210"
    # Numbers with + and spaces
    assert normalize_whatsapp_phone("+91 98765 43210") == "919876543210"
    # International numbers (e.g. US)
    assert normalize_whatsapp_phone("+1 (555) 019-2831") == "15550192831"
    # Empty or None
    assert normalize_whatsapp_phone("") == ""
    assert normalize_whatsapp_phone(None) == ""


def test_whatsapp_service_payload_builders():
    service = WhatsAppService()
    
    # Template payload
    template_payload = service.build_template_payload(
        to_phone="9876543210",
        template_name="pos_invoice_receipt",
        language_code="en_US",
        components=[{"type": "body", "parameters": [{"type": "text", "text": "INV-101"}]}],
    )
    assert template_payload["messaging_product"] == "whatsapp"
    assert template_payload["to"] == "919876543210"
    assert template_payload["type"] == "template"
    assert template_payload["template"]["name"] == "pos_invoice_receipt"
    assert template_payload["template"]["components"][0]["parameters"][0]["text"] == "INV-101"

    # Document payload
    doc_payload = service.build_document_payload(
        to_phone="9876543210",
        document_url="https://example.com/invoice.pdf",
        filename="Invoice_INV-101.pdf",
        caption="Your receipt",
    )
    assert doc_payload["type"] == "document"
    assert doc_payload["document"]["link"] == "https://example.com/invoice.pdf"
    assert doc_payload["document"]["filename"] == "Invoice_INV-101.pdf"
    assert doc_payload["document"]["caption"] == "Your receipt"

    # Text payload
    text_payload = service.build_text_payload(
        to_phone="9876543210",
        message="Hello Retail-OS!",
        preview_url=True,
    )
    assert text_payload["type"] == "text"
    assert text_payload["text"]["body"] == "Hello Retail-OS!"
    assert text_payload["text"]["preview_url"] is True


# ------------------------------------------------------------------------------
# 2. Integration Tests: Meta Webhook Handshake & Status Updates
# ------------------------------------------------------------------------------

def test_meta_webhook_verification():
    # Valid verification challenge
    resp = client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "retail_os_webhook_verify_token",
            "hub.challenge": "1158201444",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "1158201444"

    # Invalid token
    resp_invalid = client.get(
        "/api/v1/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "1158201444",
        },
    )
    assert resp_invalid.status_code == 403


def test_meta_webhook_status_delivery_update():
    db = SessionLocal()
    try:
        # Create a sample log entry
        log_entry = WhatsAppLog(
            tenant_id=1,
            recipient_phone="919876543210",
            message_type="invoice",
            meta_message_id="wamid.HBgMTestMetaId12345",
            status="sent",
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)

        # Simulate Meta Webhook payload delivery receipt: 'delivered' then 'read'
        webhook_payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"display_phone_number": "15550234567"},
                                "statuses": [
                                    {
                                        "id": "wamid.HBgMTestMetaId12345",
                                        "status": "delivered",
                                        "timestamp": "1710000000",
                                        "recipient_id": "919876543210",
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }

        post_resp = client.post("/api/v1/whatsapp/webhook", json=webhook_payload)
        assert post_resp.status_code == 200
        assert post_resp.json()["updated_statuses"] == 1

        db.refresh(log_entry)
        assert log_entry.status == "delivered"

    finally:
        db.close()


# ------------------------------------------------------------------------------
# 3. Settings & Invoices Integration Tests with Authenticated User
# ------------------------------------------------------------------------------

@pytest.fixture
def whatsapp_auth_setup(unique_slug):
    email = f"whatsapp-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "WhatsApp Test Tenant",
            "slug": unique_slug,
            "email": email,
            "admin_name": "WhatsApp Admin",
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
        json={"name": "WhatsApp Store", "code": "WAS1"},
        headers=headers,
    ).json()

    return {"headers": headers, "store": store}


def test_whatsapp_settings_crud(whatsapp_auth_setup):
    headers = whatsapp_auth_setup["headers"]

    # 1. GET Settings (defaults)
    get_res = client.get("/api/v1/whatsapp/settings", headers=headers)
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["is_enabled"] is True
    assert data["auto_send_invoice"] is True
    assert data["has_access_token"] is False

    # 2. PUT Settings (update credentials)
    update_res = client.put(
        "/api/v1/whatsapp/settings",
        json={
            "phone_number_id": "109876543210987",
            "business_account_id": "209876543210987",
            "access_token": "EAAXsampleMetaCloudApiToken12345",
            "auto_send_invoice": True,
            "template_invoice": "custom_pos_invoice",
        },
        headers=headers,
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["phone_number_id"] == "109876543210987"
    assert updated_data["template_invoice"] == "custom_pos_invoice"
    assert updated_data["has_access_token"] is True


def test_whatsapp_test_dispatch_endpoint(whatsapp_auth_setup):
    headers = whatsapp_auth_setup["headers"]

    # Configure credentials first
    client.put(
        "/api/v1/whatsapp/settings",
        json={
            "phone_number_id": "109876543210987",
            "access_token": "valid_token",
            "is_enabled": True,
        },
        headers=headers,
    )

    # Mock WhatsAppService.send_message
    with patch.object(WhatsAppService, "send_message", return_value={"status": "success", "message_id": "wamid.TEST12345"}):
        test_res = client.post(
            "/api/v1/whatsapp/test",
            json={"recipient_phone": "9876543210"},
            headers=headers,
        )
        assert test_res.status_code == 200
        assert "dispatched successfully" in test_res.json()["message"]


def test_whatsapp_send_invoice_and_logs(whatsapp_auth_setup):
    headers = whatsapp_auth_setup["headers"]
    db = SessionLocal()

    try:
        # Create customer & sample invoice using actual tenant_id
        tenant_id = whatsapp_auth_setup["store"]["tenant_id"]
        store_id = whatsapp_auth_setup["store"]["id"]

        cust = Customer(
            tenant_id=tenant_id,
            name="Ramesh Kumar",
            phone="9876500001",
            whatsapp_opt_in=True,
        )
        db.add(cust)
        db.flush()

        order = Order(
            tenant_id=tenant_id,
            store_id=store_id,
            customer_id=cust.id,
            order_number="ORD-WA-001",
            status="confirmed",
            total_amount=Decimal("1500.00"),
        )
        db.add(order)
        db.flush()

        inv = Invoice(
            tenant_id=tenant_id,
            store_id=store_id,
            order_id=order.id,
            invoice_number="INV-WA-001",
            total_amount=Decimal("1500.00"),
            status="paid",
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        # 1. Trigger WhatsApp Invoice via POST /api/v1/whatsapp/send-invoice/{id}
        with patch("app.tasks.whatsapp_tasks.send_whatsapp_invoice_task.delay") as mock_delay:
            mock_delay.return_value = MagicMock(id="task-mock-wa-001")
            send_res = client.post(
                f"/api/v1/whatsapp/send-invoice/{inv.id}",
                json={"recipient_phone": "9876500001"},
                headers=headers,
            )
            assert send_res.status_code == 200
            assert "queued" in send_res.json()["message"]
            assert send_res.json()["task_id"] == "task-mock-wa-001"

        # 2. Trigger WhatsApp Invoice via Invoices router: POST /api/v1/invoices/{id}/whatsapp
        with patch("app.tasks.whatsapp_tasks.send_whatsapp_invoice_task.delay") as mock_delay:
            mock_delay.return_value = MagicMock(id="task-mock-inv-002")
            inv_res = client.post(
                f"/api/v1/invoices/{inv.id}/whatsapp",
                headers=headers,
            )
            assert inv_res.status_code == 200
            assert "queued" in inv_res.json()["message"]

        # 3. Query Logs: GET /api/v1/whatsapp/logs
        logs_res = client.get("/api/v1/whatsapp/logs", headers=headers)
        assert logs_res.status_code == 200
        assert "items" in logs_res.json()
        assert "total" in logs_res.json()

    finally:
        db.close()
