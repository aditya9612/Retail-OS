from datetime import datetime, timedelta
from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.customer import Customer
from app.models.delivery import Delivery
from app.models.delivery_partner import DeliveryPartner
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_return import OrderReturn
from app.models.product import Product
from app.models.store import Store
from app.models.whatsapp import WhatsAppSetting
from app.services.customer_support_service import CustomerSupportService
from app.services.whatsapp_ordering_service import WhatsAppOrderingService

client = TestClient(app)


@pytest.fixture
def support_test_data():
    db = SessionLocal()
    try:
        uid = uuid.uuid4().hex[:8].upper()

        # Create Store
        store = Store(
            tenant_id=1,
            name=f"Kolhapur Store {uid[:4]}",
            code=f"KOP-{uid}",
            city="Kolhapur",
            state="Maharashtra",
            phone=f"98{uuid.uuid4().int % 100000000:08d}",
            address="Shivaji Chowk, Station Road",
            is_main=True,
            is_active=True,
        )
        db.add(store)
        db.flush()

        # Create Customer
        cust_phone = f"98{uuid.uuid4().int % 100000000:08d}"
        cust = Customer(
            tenant_id=1,
            name="Anand Patil",
            phone=cust_phone,
            whatsapp_opt_in=True,
            status="active",
        )
        db.add(cust)
        db.flush()

        # Create Product
        prod = Product(
            tenant_id=1,
            name=f"Madhur Sugar {uid[:4]}",
            sku=f"SUG-{uid}",
            selling_price=Decimal("45.00"),
            cost_price=Decimal("38.00"),
            is_active=True,
        )
        db.add(prod)
        db.flush()

        # Create Order
        ord_num = f"ORD-SUPP-{uid}"
        order = Order(
            tenant_id=1,
            store_id=store.id,
            customer_id=cust.id,
            order_number=ord_num,
            status="delivered",
            total_amount=Decimal("90.00"),
            subtotal=Decimal("90.00"),
            tax_amount=Decimal("0.00"),
            created_at=datetime.utcnow() - timedelta(days=2),
        )
        db.add(order)
        db.flush()

        # Create OrderItem
        oi = OrderItem(
            order_id=order.id,
            product_id=prod.id,
            product_name=prod.name,
            sku=prod.sku,
            quantity=2,
            unit_price=Decimal("45.00"),
            total_amount=Decimal("90.00"),
        )
        db.add(oi)
        db.flush()

        # Create Delivery Partner & Delivery
        dp = DeliveryPartner(
            tenant_id=1,
            name="Shadowfax Express",
            code=f"SFX-{uid}",
            contact_phone="9988776655",
            is_active=True,
        )
        db.add(dp)
        db.flush()

        deliv = Delivery(
            tenant_id=1,
            order_id=order.id,
            partner_id=dp.id,
            tracking_number=f"TRK-{uid}",
            status="delivered",
            estimated_delivery_time=datetime.utcnow() + timedelta(hours=3),
        )
        db.add(deliv)
        db.flush()

        # Create Invoice
        inv_num = f"INV-SUPP-{uid}"
        inv = Invoice(
            tenant_id=1,
            store_id=store.id,
            order_id=order.id,
            invoice_number=inv_num,
            total_amount=Decimal("90.00"),
            status="paid",
        )
        db.add(inv)
        db.commit()

        return {
            "tenant_id": 1,
            "store_id": store.id,
            "store_name": store.name,
            "customer_id": cust.id,
            "customer_phone": cust_phone,
            "order_id": order.id,
            "order_number": ord_num,
            "invoice_number": inv_num,
            "product_id": prod.id,
            "product_name": prod.name,
        }
    finally:
        db.close()


# ------------------------------------------------------------------------------
# 1. LIVE ORDER TRACKING TESTS
# ------------------------------------------------------------------------------

def test_track_order_direct_api(support_test_data):
    ord_num = support_test_data["order_number"]
    res = client.get(f"/api/v1/support/track-order/{ord_num}")
    assert res.status_code == 200
    data = res.json()
    assert data["order_number"] == ord_num
    assert data["status"] == "delivered"
    assert data["delivery_partner"] == "Shadowfax Express"
    assert "TRK-" in data["tracking_number"]
    assert data["is_return_eligible"] is True
    assert len(data["items"]) >= 1
    assert data["items"][0]["product_name"] == support_test_data["product_name"]


def test_track_order_not_found():
    res = client.get("/api/v1/support/track-order/ORD-NONEXISTENT-999")
    assert res.status_code == 404


# ------------------------------------------------------------------------------
# 2. INVOICE RE-FETCH & DOWNLOAD TESTS
# ------------------------------------------------------------------------------

def test_get_invoice_direct_by_invoice_and_order_number(support_test_data):
    inv_num = support_test_data["invoice_number"]
    ord_num = support_test_data["order_number"]

    # 1. By Invoice Number
    res1 = client.get(f"/api/v1/support/invoice/{inv_num}")
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["invoice_number"] == inv_num
    assert "/api/v1/invoices/" in data1["pdf_url"]
    assert data1["total_amount"] == 90.0

    # 2. By Order Number
    res2 = client.get(f"/api/v1/support/invoice/{ord_num}")
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["invoice_number"] == inv_num


# ------------------------------------------------------------------------------
# 3. SELF-SERVICE RETURN REQUEST TESTS
# ------------------------------------------------------------------------------

def test_initiate_return_request_success(support_test_data):
    ord_num = support_test_data["order_number"]
    phone = support_test_data["customer_phone"]

    payload = {
        "order_number": ord_num,
        "customer_phone": phone,
        "reason": "Damaged packaging / seal broken",
        "refund_preference": "store_credit",
        "items": [
            {
                "product_id": support_test_data["product_id"],
                "quantity": 1,
                "reason": "Packet leaking",
            }
        ],
    }
    res = client.post("/api/v1/support/returns/initiate", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert "return_id" in data
    assert data["order_number"] == ord_num
    assert data["status"] in ["requested", "pending"]
    assert data["total_refund_amount"] > 0
    assert "Return request initiated successfully" in data["message"]


def test_initiate_return_phone_mismatch_fails(support_test_data):
    ord_num = support_test_data["order_number"]
    payload = {
        "order_number": ord_num,
        "customer_phone": "9999900000",
        "reason": "Wrong item",
    }
    res = client.post("/api/v1/support/returns/initiate", json=payload)
    assert res.status_code == 400
    assert "Phone number does not match" in res.text


# ------------------------------------------------------------------------------
# 4. STORE FAQ & INFORMATION TESTS
# ------------------------------------------------------------------------------

def test_store_faq_api(support_test_data):
    res = client.get("/api/v1/support/faq?tenant_id=1")
    assert res.status_code == 200
    data = res.json()
    assert "store_name" in data
    assert "operating_hours" in data
    assert "payment_methods" in data
    assert "return_policy" in data


# ------------------------------------------------------------------------------
# 5. NATURAL LANGUAGE AI SUPPORT CHAT QUERY TESTS
# ------------------------------------------------------------------------------

def test_support_chat_greeting():
    res = client.post(
        "/api/v1/support/chat",
        json={"query": "नमस्ते! मला मदत हवी आहे"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "greeting"
    assert "24/7 AI ग्राहक सेवा" in data["reply"] or "AI ग्राहक सहाय्यक" in data["reply"]
    assert len(data["suggested_actions"]) > 0


def test_support_chat_order_tracking(support_test_data):
    ord_num = support_test_data["order_number"]
    res = client.post(
        "/api/v1/support/chat",
        json={"query": f"माझी ऑर्डर {ord_num} कुठे आहे?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "order_tracking"
    assert ord_num in data["reply"]
    assert "Shadowfax Express" in data["reply"] or "स्थिती" in data["reply"]


def test_support_chat_invoice_download(support_test_data):
    ord_num = support_test_data["order_number"]
    res = client.post(
        "/api/v1/support/chat",
        json={"query": f"मला {ord_num} चे टॅक्स इनव्हॉइस बिल डाऊनलोड करायचे आहे"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "invoice_download"
    assert support_test_data["invoice_number"] in data["reply"]
    assert "Download Tax Invoice PDF" in data["reply"]


def test_support_chat_store_timing_and_address():
    res = client.post(
        "/api/v1/support/chat",
        json={"query": "दुकान कधी उघडे असते आणि पत्ता काय आहे?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "faq_store_info"
    assert "पत्ता" in data["reply"]
    assert "दुकान वेळ" in data["reply"]


# ------------------------------------------------------------------------------
# 6. STANDALONE WEB CHAT WIDGET TEST
# ------------------------------------------------------------------------------

def test_support_widget_html():
    res = client.get("/api/v1/support/widget")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Retail-OS | 24/7 AI Customer Support & Returns Bot" in res.text
    assert "chatBox" in res.text

    # Shortcut link redirect test
    res_short = client.get("/support-widget", follow_redirects=False)
    assert res_short.status_code in [302, 307]


# ------------------------------------------------------------------------------
# 7. WHATSAPP CONVERSATIONAL SUPPORT HOOK TEST
# ------------------------------------------------------------------------------

def test_whatsapp_inbound_support_inquiry(support_test_data):
    db = SessionLocal()
    try:
        ord_num = support_test_data["order_number"]
        phone = support_test_data["customer_phone"]

        # Ensure setting is active
        setting = db.query(WhatsAppSetting).filter(WhatsAppSetting.tenant_id == 1).first()
        if not setting:
            setting = WhatsAppSetting(tenant_id=1, is_enabled=True, ai_ordering_enabled=True)
            db.add(setting)
            db.commit()

        ordering_svc = WhatsAppOrderingService(db=db)
        res = ordering_svc.process_inbound_message(
            from_phone=phone,
            message_body=f"माझी ऑर्डर {ord_num} कुठे आहे आणि डिलिव्हरी स्टेटस सांगा",
            sender_name="Anand Patil",
            tenant_id=1,
        )

        assert res["status"] == "success"
        assert res["intent"] in ["order_tracking", "status"]
        assert ord_num in res["reply"]

    finally:
        db.close()
