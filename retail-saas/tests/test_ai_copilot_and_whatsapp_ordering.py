from decimal import Decimal
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.models.category import Category
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.store import Store
from app.models.whatsapp import WhatsAppSetting, WhatsAppLog
from app.services.ai_service import AIService
from app.services.whatsapp_ordering_service import WhatsAppOrderingService
from app.services.whatsapp_service import WhatsAppService
from app.utils.constants import OrderStatus

client = TestClient(app)


@pytest.fixture
def copilot_and_ordering_setup(unique_slug):
    email = f"copilot-{unique_slug}@test.com"
    client.post(
        "/api/v1/auth/register",
        params={
            "tenant_name": "AI Retail Enterprise",
            "slug": unique_slug,
            "email": email,
            "admin_name": "Retail Copilot Admin",
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
        json={"name": "Shivaji Supermarket", "code": "SSM-01", "phone": "9876543210"},
        headers=headers,
    ).json()

    tenant_id = store["tenant_id"]
    store_id = store["id"]

    db = SessionLocal()
    try:
        # 1. Categories
        cat_grocery = Category(tenant_id=tenant_id, name="Groceries", is_active=True)
        cat_dairy = Category(tenant_id=tenant_id, name="Dairy & Bakery", is_active=True)
        cat_snacks = Category(tenant_id=tenant_id, name="Snacks & Sweets", is_active=True)
        db.add_all([cat_grocery, cat_dairy, cat_snacks])
        db.flush()

        # 2. Products
        p_sugar = Product(
            tenant_id=tenant_id,
            category_id=cat_grocery.id,
            name="Madhur Pure Sugar",
            sku="SUG-001",
            selling_price=Decimal("45.00"),
            cost_price=Decimal("38.00"),
            unit="kg",
            is_active=True,
        )
        p_milk = Product(
            tenant_id=tenant_id,
            category_id=cat_dairy.id,
            name="Amul Taaza Milk 1L",
            sku="MLK-001",
            selling_price=Decimal("56.00"),
            cost_price=Decimal("48.00"),
            unit="ltr",
            is_active=True,
        )
        p_bread = Product(
            tenant_id=tenant_id,
            category_id=cat_dairy.id,
            name="Wibs Brown Bread",
            sku="BRD-001",
            selling_price=Decimal("40.00"),
            cost_price=Decimal("32.00"),
            unit="pcs",
            is_active=True,
        )
        db.add_all([p_sugar, p_milk, p_bread])
        db.flush()

        # 3. Customer with Khata / Credit Balance > ₹1000
        cust_credit_high = Customer(
            tenant_id=tenant_id,
            name="Suresh Patil",
            phone="9822012345",
            outstanding_balance=Decimal("2450.00"),
            credit_limit=Decimal("5000.00"),
            whatsapp_opt_in=True,
            status="active",
        )
        cust_credit_low = Customer(
            tenant_id=tenant_id,
            name="Amit Jadhav",
            phone="9822099999",
            outstanding_balance=Decimal("450.00"),
            credit_limit=Decimal("2000.00"),
            whatsapp_opt_in=True,
            status="active",
        )
        db.add_all([cust_credit_high, cust_credit_low])
        db.flush()

        # 4. WhatsApp Configuration with AI Ordering Enabled & UPI
        wa_setting = (
            db.query(WhatsAppSetting)
            .filter(WhatsAppSetting.tenant_id == tenant_id, WhatsAppSetting.store_id.is_(None))
            .first()
        )
        if not wa_setting:
            wa_setting = WhatsAppSetting(
                tenant_id=tenant_id,
                store_id=store_id,
            )
            db.add(wa_setting)

        wa_setting.phone_number_id = "109876543210999"
        wa_setting.access_token = "mock_valid_token"
        wa_setting.is_enabled = True
        wa_setting.ai_ordering_enabled = True
        wa_setting.upi_vpa = "shivaji.store@icici"
        wa_setting.upi_payee_name = "Shivaji Supermarket"
        db.commit()

        return {
            "headers": headers,
            "tenant_id": tenant_id,
            "store_id": store_id,
            "p_sugar_id": p_sugar.id,
            "p_milk_id": p_milk.id,
            "p_bread_id": p_bread.id,
            "cust_high_id": cust_credit_high.id,
            "phone_number_id": wa_setting.phone_number_id,
        }
    finally:
        db.close()


# ==============================================================================
# 1. Tests for Feature A: Gemini AI Retail Copilot (मराठी & इंग्रजी)
# ==============================================================================

def test_copilot_category_drop_analysis(copilot_and_ordering_setup):
    headers = copilot_and_ordering_setup["headers"]
    store_id = copilot_and_ordering_setup["store_id"]

    # Question in Marathi: "मागच्या आठवड्यापेक्षा या आठवड्यात कोणत्या कॅटेगरीचा सेल कमी झाला आणि का?"
    resp = client.post(
        "/api/v1/ai/chat-query",
        json={
            "query": "मागच्या आठवड्यापेक्षा या आठवड्यात कोणत्या कॅटेगरीचा सेल कमी झाला आणि का?",
            "store_id": store_id,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["intent"] == "category_drop_analysis"
    assert "कॅटेगरी" in data["answer"]
    assert len(data["suggested_actions"]) > 0
    assert any("category" in act.lower() or "coupon" in act.lower() for act in data["suggested_actions"])


def test_copilot_diwali_festival_stocking(copilot_and_ordering_setup):
    headers = copilot_and_ordering_setup["headers"]
    store_id = copilot_and_ordering_setup["store_id"]

    # Question in Marathi: "दिवाळीसाठी मला कोणत्या ५ प्रॉडक्ट्सचा स्टॉक जास्त मागवावा लागेल?"
    resp = client.post(
        "/api/v1/ai/chat-query",
        json={
            "query": "दिवाळीसाठी मला कोणत्या ५ प्रॉडक्ट्सचा स्टॉक जास्त मागवावा लागेल?",
            "store_id": store_id,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["intent"] == "festival_reorder_recommendation"
    assert "दिवाळी" in data["answer"] or "सण" in data["answer"]
    assert "साखर" in data["answer"] or "Sugar" in data["answer"] or "स्टॉक" in data["answer"]
    assert any("purchase order" in act.lower() or "order" in act.lower() for act in data["suggested_actions"])


def test_copilot_credit_khata_over_1000_reminders(copilot_and_ordering_setup):
    headers = copilot_and_ordering_setup["headers"]
    store_id = copilot_and_ordering_setup["store_id"]

    # Question in Marathi: "१००० रुपयांपेक्षा जास्त उधारी बाकी असलेल्या ग्राहकांची यादी दाखव आणि त्यांना रिमाइंडर्स पाठव."
    resp = client.post(
        "/api/v1/ai/chat-query",
        json={
            "query": "१००० रुपयांपेक्षा जास्त उधारी बाकी असलेल्या ग्राहकांची यादी दाखव आणि त्यांना रिमाइंडर्स पाठव.",
            "store_id": store_id,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["intent"] == "credit_khata_reminders"
    assert "उधारी" in data["answer"] or "खातेदार" in data["answer"]
    # Suresh Patil has 2450.00 outstanding
    assert "Suresh Patil" in data["answer"] or "2,450" in data["answer"] or "2450" in data["answer"]
    assert any("whatsapp" in act.lower() for act in data["suggested_actions"])
    assert "credit_over_1000_customers" in data["data"]


def test_copilot_gemini_api_call_mock(copilot_and_ordering_setup):
    headers = copilot_and_ordering_setup["headers"]

    mock_gemini_response = {
        "intent": "copilot_gemini_insight",
        "answer": "Gemini AI: दिवाळीच्या काळात ग्राहकांची वर्दळ वाढणार असल्याने ५ आवश्यक प्रॉडक्ट्सचा अतिरिक्त स्टॉक ठेवावा.",
        "data": {"forecast_factor": 1.45},
        "suggested_actions": ["Review festive inventory", "Contact distributor"],
    }

    from app.services import ai_service
    with patch.object(ai_service.settings, "GEMINI_API_KEY", "mock_gemini_key"):
        with patch.object(AIService, "_call_gemini_copilot", return_value={
            "query": "दिवाळीची तयारी",
            **mock_gemini_response
        }):
            resp = client.post(
                "/api/v1/ai/chat-query",
                json={"query": "दिवाळीची तयारी"},
                headers=headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["intent"] == "copilot_gemini_insight"
            assert "Gemini AI" in data["answer"]


# ==============================================================================
# 2. Tests for Feature B: WhatsApp AI Conversational Ordering (चॅटबॉट POS)
# ==============================================================================

def test_whatsapp_conversational_ordering_flow(copilot_and_ordering_setup):
    db = SessionLocal()
    phone_number_id = copilot_and_ordering_setup["phone_number_id"]
    customer_phone = "919988776655"

    try:
        # Customer sends message in Marathi:
        # "मला १ किलो साखर, २ लिटर अमूल दूध आणि १ ब्रेड घरी पाठवा"
        order_msg_payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA_ID_TEST",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "15550234567",
                                    "phone_number_id": phone_number_id,
                                },
                                "contacts": [
                                    {
                                        "profile": {"name": "Gaurav Dhaygude"},
                                        "wa_id": customer_phone,
                                    }
                                ],
                                "messages": [
                                    {
                                        "from": customer_phone,
                                        "id": "wamid.TEST_ORDER_MSG_001",
                                        "timestamp": "1710000000",
                                        "type": "text",
                                        "text": {
                                            "body": "मला १ किलो साखर, २ लिटर अमूल दूध आणि १ ब्रेड घरी पाठवा"
                                        },
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }

        with patch.object(WhatsAppService, "send_message", return_value={"status": "success", "message_id": "wamid.OUT_REPLY_001"}) as mock_send:
            resp = client.post("/api/v1/whatsapp/webhook", json=order_msg_payload)
            assert resp.status_code == 200, resp.text
            res_data = resp.json()
            assert res_data["status"] == "success"
            assert res_data["processed_messages"] == 1

            # Check order result details
            order_res = res_data["results"][0]
            assert order_res["status"] == "success"
            assert order_res["intent"] == "order_created"
            assert "order_id" in order_res
            assert "upi_link" in order_res
            assert "upi://pay?" in order_res["upi_link"]
            assert "shivaji.store@icici" in order_res["upi_link"]

            # Verify outbound WhatsApp message dispatched back to customer
            assert mock_send.called
            call_args = mock_send.call_args
            to_arg, text_arg = call_args[0][0], call_args[0][1]
            assert to_arg == customer_phone
            assert "ऑर्डर तयार झाली" in text_arg
            assert "Sugar" in text_arg or "साखर" in text_arg
            assert "Milk" in text_arg or "दूध" in text_arg
            assert "Bread" in text_arg or "ब्रेड" in text_arg
            assert "upi://pay?" in text_arg

            # Verify database Order and OrderItem were persisted
            created_order = db.query(Order).filter(Order.id == order_res["order_id"]).first()
            assert created_order is not None
            assert created_order.customer is not None
            assert created_order.customer.phone.endswith("9988776655")
            # 3 items: Sugar (1 kg) + Milk (2 ltr) + Bread (1 pcs)
            assert len(created_order.items) == 3
            # 1 sugar (45) + 2 milk (56*2 = 112) + 1 bread (40) = 197.00
            assert created_order.total_amount == Decimal("197.00")

    finally:
        db.close()


def test_whatsapp_conversational_greeting_menu(copilot_and_ordering_setup):
    phone_number_id = copilot_and_ordering_setup["phone_number_id"]
    customer_phone = "919988776655"

    greeting_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": phone_number_id},
                            "contacts": [{"profile": {"name": "Pooja"}, "wa_id": customer_phone}],
                            "messages": [
                                {
                                    "from": customer_phone,
                                    "id": "wamid.GREETING_001",
                                    "type": "text",
                                    "text": {"body": "नमस्कार, मला ऑर्डर करायची आहे"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    with patch.object(WhatsAppService, "send_message", return_value={"status": "success", "message_id": "wamid.GREET_REPLY"}):
        resp = client.post("/api/v1/whatsapp/webhook", json=greeting_payload)
        assert resp.status_code == 200
        res_data = resp.json()
        assert res_data["results"][0]["intent"] == "greeting"
        assert "स्वागत आहे" in res_data["results"][0]["reply"]


def test_whatsapp_conversational_status_inquiry(copilot_and_ordering_setup):
    phone_number_id = copilot_and_ordering_setup["phone_number_id"]
    customer_phone = "919988776655"

    status_payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": phone_number_id},
                            "contacts": [{"profile": {"name": "Gaurav"}, "wa_id": customer_phone}],
                            "messages": [
                                {
                                    "from": customer_phone,
                                    "id": "wamid.STATUS_001",
                                    "type": "text",
                                    "text": {"body": "माझी ऑर्डर कुठे आहे? status सांगा"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    with patch.object(WhatsAppService, "send_message", return_value={"status": "success", "message_id": "wamid.STATUS_REPLY"}):
        resp = client.post("/api/v1/whatsapp/webhook", json=status_payload)
        assert resp.status_code == 200
        res_data = resp.json()
        assert res_data["results"][0]["intent"] == "status"
        assert "ऑर्डर स्थिती" in res_data["results"][0]["reply"]
