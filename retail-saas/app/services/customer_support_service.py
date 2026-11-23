from datetime import datetime, timedelta
from decimal import Decimal
import json
import re
from typing import Any, Dict, List, Optional, Tuple
import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppException, NotFoundException
from app.core.logger import logger
from app.models.customer import Customer
from app.models.delivery import Delivery
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_return import OrderReturn, OrderReturnItem
from app.models.product import Product
from app.models.store import Store
from app.models.tenant import Tenant
from app.schemas.customer_support import (
    CustomerInvoiceDownloadResponse,
    CustomerOrderTrackResponse,
    CustomerReturnResponse,
    CustomerSupportQueryResponse,
    OrderItemSummary,
    ReturnItemDetail,
)
from app.services.whatsapp_service import normalize_whatsapp_phone
from app.utils.constants import OrderStatus

settings = get_settings()


class CustomerSupportService:
    def __init__(self, db: Session, tenant_id: Optional[int] = None, store_id: Optional[int] = None):
        self.db = db
        self.tenant_id = tenant_id or 1
        self.store_id = store_id

    def _resolve_context(self) -> Tuple[Tenant, Optional[Store]]:
        tenant = self.db.query(Tenant).filter(Tenant.id == self.tenant_id).first()
        store = None
        if self.store_id:
            store = self.db.query(Store).filter(Store.id == self.store_id, Store.tenant_id == self.tenant_id).first()
        if not store:
            store = (
                self.db.query(Store)
                .filter(Store.tenant_id == self.tenant_id, Store.is_active.is_(True))
                .order_by(Store.is_main.desc(), Store.id.asc())
                .first()
            )
        return tenant, store

    # --------------------------------------------------------------------------
    # 1. LIVE ORDER TRACKING
    # --------------------------------------------------------------------------

    def track_order(
        self, order_number: Optional[str] = None, customer_phone: Optional[str] = None
    ) -> CustomerOrderTrackResponse:
        """Finds live status, items, delivery partner, and tracking link for an order."""
        query = self.db.query(Order).filter(Order.tenant_id == self.tenant_id)

        target_order: Optional[Order] = None
        if order_number and order_number.strip():
            clean_ord = order_number.strip().upper()
            target_order = query.filter(func_upper_order(clean_ord)).first()

        if not target_order and customer_phone:
            clean_phone = normalize_whatsapp_phone(customer_phone)
            short_phone = clean_phone[-10:] if len(clean_phone) >= 10 else clean_phone
            cust = (
                self.db.query(Customer)
                .filter(
                    Customer.tenant_id == self.tenant_id,
                    (Customer.phone == clean_phone) | (Customer.phone == short_phone),
                )
                .first()
            )
            if cust:
                target_order = (
                    query.filter(Order.customer_id == cust.id)
                    .order_by(Order.id.desc())
                    .first()
                )

        if not target_order:
            raise NotFoundException(
                f"Order '{order_number or customer_phone}' not found in our records."
            )

        # Delivery Information
        delivery = self.db.query(Delivery).filter(Delivery.order_id == target_order.id).first()
        delivery_status = delivery.status if delivery else None
        partner_name = delivery.partner.name if delivery and delivery.partner else None
        tracking_num = delivery.tracking_number if delivery else None
        eta = delivery.estimated_delivery_time.strftime("%d %b %Y, %I:%M %p") if delivery and delivery.estimated_delivery_time else None

        # Return Eligibility: delivered within last 14 days
        delivered_statuses = [OrderStatus.DELIVERED.value, "completed", "delivered"]
        is_delivered = target_order.status.lower() in delivered_statuses
        days_since = (datetime.utcnow() - target_order.created_at).days
        is_return_eligible = is_delivered and days_since <= 14

        # Invoice Link
        invoice = self.db.query(Invoice).filter(Invoice.order_id == target_order.id).first()
        base_url = settings.APP_BASE_URL.rstrip("/")
        invoice_pdf_url = f"{base_url}/api/v1/invoices/{invoice.id}/pdf" if invoice else None

        # Items
        items_summary = []
        for it in target_order.items:
            items_summary.append(
                OrderItemSummary(
                    product_name=it.product_name or (it.product.name if it.product else "Item"),
                    quantity=float(it.quantity),
                    unit_price=float(it.unit_price or 0.0),
                    total=float(it.total_amount or it.total or 0.0),
                )
            )

        status_desc = self._get_status_description(target_order.status, delivery_status, eta)

        return CustomerOrderTrackResponse(
            order_id=target_order.id,
            order_number=target_order.order_number,
            status=target_order.status,
            total_amount=float(target_order.total_amount),
            order_date=target_order.created_at,
            items=items_summary,
            delivery_status=delivery_status,
            delivery_partner=partner_name,
            tracking_number=tracking_num,
            estimated_delivery=eta,
            invoice_pdf_url=invoice_pdf_url,
            is_return_eligible=is_return_eligible,
            status_description=status_desc,
        )

    # --------------------------------------------------------------------------
    # 2. INVOICE RE-FETCH & DOWNLOAD
    # --------------------------------------------------------------------------

    def get_invoice_download(
        self, order_or_invoice: str, customer_phone: Optional[str] = None
    ) -> CustomerInvoiceDownloadResponse:
        """Looks up tax invoice by invoice number, order number, or latest customer phone."""
        clean_input = order_or_invoice.strip().upper()
        base_url = settings.APP_BASE_URL.rstrip("/")

        invoice = (
            self.db.query(Invoice)
            .filter(
                Invoice.tenant_id == self.tenant_id,
                (Invoice.invoice_number == clean_input) | (Invoice.invoice_number.ilike(f"%{clean_input}%")),
            )
            .first()
        )

        if not invoice:
            order = (
                self.db.query(Order)
                .filter(Order.tenant_id == self.tenant_id, Order.order_number == clean_input)
                .first()
            )
            if order:
                invoice = self.db.query(Invoice).filter(Invoice.order_id == order.id).first()

        if not invoice and customer_phone:
            clean_phone = normalize_whatsapp_phone(customer_phone)
            short_phone = clean_phone[-10:] if len(clean_phone) >= 10 else clean_phone
            cust = (
                self.db.query(Customer)
                .filter(
                    Customer.tenant_id == self.tenant_id,
                    (Customer.phone == clean_phone) | (Customer.phone == short_phone),
                )
                .first()
            )
            if cust:
                order = (
                    self.db.query(Order)
                    .filter(Order.customer_id == cust.id)
                    .order_by(Order.id.desc())
                    .first()
                )
                if order:
                    invoice = self.db.query(Invoice).filter(Invoice.order_id == order.id).first()

        if not invoice:
            raise NotFoundException(f"Invoice for '{order_or_invoice}' not found.")

        pdf_path = f"/api/v1/invoices/{invoice.id}/pdf"
        full_pdf_url = f"{base_url}{pdf_path}"
        ord_num = invoice.order.order_number if invoice.order else "ORD"

        return CustomerInvoiceDownloadResponse(
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
            order_number=ord_num,
            total_amount=float(invoice.total_amount),
            date=invoice.created_at,
            pdf_url=pdf_path,
            download_link=full_pdf_url,
            status=invoice.status,
        )

    # --------------------------------------------------------------------------
    # 3. SELF-SERVICE RETURN REQUEST INITIATION
    # --------------------------------------------------------------------------

    def initiate_customer_return(
        self,
        order_number: str,
        customer_phone: str,
        reason: str,
        items: Optional[List[ReturnItemDetail]] = None,
        remarks: Optional[str] = None,
        refund_preference: str = "store_credit",
    ) -> CustomerReturnResponse:
        """Validates order return policy window and creates an official OrderReturn request."""
        clean_ord = order_number.strip().upper()
        order = (
            self.db.query(Order)
            .filter(Order.tenant_id == self.tenant_id, Order.order_number == clean_ord)
            .first()
        )
        if not order:
            raise NotFoundException(f"Order '{order_number}' not found.")

        # Phone Verification
        clean_phone = normalize_whatsapp_phone(customer_phone)
        short_phone = clean_phone[-10:] if len(clean_phone) >= 10 else clean_phone
        customer = order.customer
        if customer:
            cust_phone_clean = normalize_whatsapp_phone(customer.phone)
            cust_short = cust_phone_clean[-10:] if len(cust_phone_clean) >= 10 else cust_phone_clean
            if short_phone != cust_short:
                raise AppException("Phone number does not match the order customer record.")
        else:
            customer = self.db.query(Customer).filter(Customer.tenant_id == self.tenant_id, Customer.phone == short_phone).first()
            if not customer:
                customer = Customer(
                    tenant_id=self.tenant_id,
                    name=f"Customer {short_phone[-4:]}",
                    phone=short_phone,
                    whatsapp_opt_in=True,
                )
                self.db.add(customer)
                self.db.flush()

        # Eligibility Window (14 days)
        days_since = (datetime.utcnow() - order.created_at).days
        if days_since > 14:
            raise AppException(
                f"Order #{order_number} is past the 14-day return window ({days_since} days ago). "
                f"Please contact store support for special assistance."
            )

        # Existing pending return check
        existing_return = (
            self.db.query(OrderReturn)
            .filter(
                OrderReturn.tenant_id == self.tenant_id,
                OrderReturn.order_id == order.id,
                OrderReturn.status.in_(["requested", "pending", "approved"]),
            )
            .first()
        )
        if existing_return:
            return CustomerReturnResponse(
                return_id=existing_return.id,
                return_number=existing_return.return_number or f"RET-{existing_return.id}",
                order_number=order.order_number,
                status=existing_return.status,
                total_refund_amount=float(existing_return.total_amount),
                refund_preference=refund_preference,
                created_at=existing_return.created_at,
                message=f"Return request #{existing_return.return_number} is already active for this order.",
            )

        # Calculate refund amount & items
        total_refund = Decimal("0.00")
        items_to_create = []

        if items:
            for req_item in items:
                matched_oi = None
                for oi in order.items:
                    if req_item.order_item_id and oi.id == req_item.order_item_id:
                        matched_oi = oi
                        break
                    elif req_item.product_id and oi.product_id == req_item.product_id:
                        matched_oi = oi
                        break
                    elif req_item.product_name and req_item.product_name.lower() in (oi.product_name or "").lower():
                        matched_oi = oi
                        break

                if not matched_oi and order.items:
                    matched_oi = order.items[0]

                if matched_oi:
                    ret_qty = min(int(req_item.quantity), int(matched_oi.quantity))
                    u_price = matched_oi.unit_price or Decimal("0.00")
                    sub = u_price * Decimal(str(ret_qty))
                    total_refund += sub
                    items_to_create.append({
                        "order_item_id": matched_oi.id,
                        "product_id": matched_oi.product_id,
                        "quantity": ret_qty,
                        "unit_price": u_price,
                        "total_amount": sub,
                    })
        else:
            # Return all items
            for oi in order.items:
                sub = (oi.unit_price or Decimal("0.00")) * Decimal(str(oi.quantity))
                total_refund += sub
                items_to_create.append({
                    "order_item_id": oi.id,
                    "product_id": oi.product_id,
                    "quantity": int(oi.quantity),
                    "unit_price": oi.unit_price or Decimal("0.00"),
                    "total_amount": sub,
                })

        if total_refund == Decimal("0.00") and order.total_amount > Decimal("0.00"):
            total_refund = order.total_amount

        # Create OrderReturn
        new_return = OrderReturn(
            tenant_id=self.tenant_id,
            order_id=order.id,
            customer_id=customer.id,
            return_type="refund",
            reason=reason,
            remarks=f"Self-service return via AI Support Bot. Mode: {refund_preference}. {remarks or ''}".strip(),
            status="requested",
            total_amount=total_refund,
            refund_amount=total_refund,
        )
        self.db.add(new_return)
        self.db.flush()

        for it in items_to_create:
            ret_item = OrderReturnItem(
                tenant_id=self.tenant_id,
                order_return_id=new_return.id,
                order_item_id=it["order_item_id"],
                product_id=it["product_id"],
                quantity=it["quantity"],
                unit_price=it["unit_price"],
                total_amount=it["total_amount"],
                reason=reason,
            )
            self.db.add(ret_item)

        self.db.commit()
        self.db.refresh(new_return)

        return CustomerReturnResponse(
            return_id=new_return.id,
            return_number=new_return.return_number or f"RET-{new_return.id}",
            order_number=order.order_number,
            status=new_return.status,
            total_refund_amount=float(total_refund),
            refund_preference=refund_preference,
            created_at=new_return.created_at,
            message="Return request initiated successfully. Our support team will inspect and process your refund/store credit.",
        )

    # --------------------------------------------------------------------------
    # 4. STORE FAQ & INFORMATION
    # --------------------------------------------------------------------------

    def get_store_faq(self) -> Dict[str, Any]:
        """Provides dynamic store facts: address, timings, payment modes, contact."""
        tenant, store = self._resolve_context()
        s_name = store.name if store else (tenant.name if tenant else "Retail Store")
        s_city = store.city if store else "Maharashtra"
        s_addr = store.address if store else "Main Market Road"
        s_phone = store.phone if store else "9876543210"
        s_email = store.email if store else "support@retailos.com"

        return {
            "store_name": s_name,
            "address": f"{s_addr}, {s_city}",
            "city": s_city,
            "phone": s_phone,
            "email": s_email,
            "operating_hours": "सोमवार ते रविवार: सकाळी ८:०० ते रात्री १०:०० (Daily 8:00 AM - 10:00 PM)",
            "payment_methods": "UPI (Google Pay, PhonePe, Paytm), Cash on Delivery, Cards, Khata / Store Credit",
            "whatsapp_ordering": f"होय! आपण {s_phone} या नंबरवर किराणा यादी किंवा चिठ्ठीचा फोटो पाठवून ऑर्डर करू शकता.",
            "return_policy": "वस्तू मिळाल्यापासून १४ दिवसांच्या आत सहज रिटर्न किंवा एक्सचेंज सुविधा उपलब्ध आहे.",
        }

    # --------------------------------------------------------------------------
    # 5. NATURAL LANGUAGE AI DISPATCHER (MARATHI / HINDI / ENGLISH)
    # --------------------------------------------------------------------------

    def process_query(
        self,
        query: str,
        customer_phone: Optional[str] = None,
        order_number: Optional[str] = None,
        language: str = "mr",
    ) -> CustomerSupportQueryResponse:
        """Processes customer questions using Gemini GenAI with deterministic fallback."""
        q_clean = query.strip()
        tenant, store = self._resolve_context()
        store_name = store.name if store else (tenant.name if tenant else "Retail Store")

        # Extract explicit order or invoice number if typed in query (e.g. ORD-1001, ORD-SUPP-12345, INV-1001)
        extracted_ord = order_number
        if not extracted_ord:
            ord_match = re.search(r"\b((?:ORD|INV)[-_A-Z0-9]+)\b", q_clean, re.IGNORECASE)
            if ord_match:
                extracted_ord = ord_match.group(1).upper()

        q_lower = q_clean.lower()

        # ---------------------------------------------------------
        # A. INTENT: ORDER TRACKING
        # ---------------------------------------------------------
        track_keywords = [
            "track", "status", "कुठे आहे", "ऑर्डर", "कधी येईल", "पोहोचली",
            "पार्सल", "delivery", "कधी मिळणार", "order status", "where is my order",
        ]
        if any(k in q_lower for k in track_keywords) and not any(k in q_lower for k in ["return", "रिटर्न", "बिल", "invoice"]):
            if extracted_ord or customer_phone:
                try:
                    track_data = self.track_order(extracted_ord, customer_phone)
                    reply = (
                        f"📦 *ऑर्डर स्थिती (Order Status) - #{track_data.order_number}*\n\n"
                        f"• **सध्याची स्थिती:** *{track_data.status.upper()}*\n"
                        f"• **तपशील:** {track_data.status_description}\n"
                        f"• **एकूण रक्कम:** ₹{track_data.total_amount:,.2f}\n"
                        f"• **ऑर्डर तारीख:** {track_data.order_date.strftime('%d %b %Y, %I:%M %p')}\n"
                    )
                    if track_data.delivery_partner:
                        reply += f"• **डिलिव्हरी पार्टनर:** {track_data.delivery_partner}\n"
                    if track_data.tracking_number:
                        reply += f"• **ट्रॅकिंग नंबर:** `{track_data.tracking_number}`\n"
                    if track_data.estimated_delivery:
                        reply += f"• **अंदाजे वेळ:** {track_data.estimated_delivery}\n"

                    actions = ["Download Invoice PDF", "Return / Exchange Item", "Contact Store"]
                    speech = f"आपली ऑर्डर क्रमांक {track_data.order_number} सध्या {track_data.status} स्थितीत आहे."
                    return CustomerSupportQueryResponse(
                        intent="order_tracking",
                        reply=reply,
                        speech_text=speech,
                        data=track_data.model_dump(),
                        suggested_actions=actions,
                    )
                except Exception as exc:
                    logger.info("Order track failed for query: %s", exc)

            # Ask for Order Number
            reply = (
                f"नमस्ते! आपल्या ऑर्डरची नेमकी स्थिती जाणून घेण्यासाठी कृपया आपला **ऑर्डर क्रमांक** "
                f"(उदा. *ORD-1001*) किंवा नोंदणीकृत **मोबाईल नंबर** येथे टाईप करा."
            )
            return CustomerSupportQueryResponse(
                intent="order_tracking",
                reply=reply,
                speech_text="कृपया आपला ऑर्डर क्रमांक किंवा मोबाईल नंबर सांगा.",
                suggested_actions=["Track latest order with phone", "View my past orders"],
            )

        # ---------------------------------------------------------
        # B. INTENT: INVOICE / BILL DOWNLOAD
        # ---------------------------------------------------------
        bill_keywords = ["bill", "invoice", "पावती", "बिल", "पावती हवी", "tax invoice", "receipt", "रसीद"]
        if any(k in q_lower for k in bill_keywords):
            target_id = extracted_ord
            if not target_id:
                for token in q_clean.split():
                    clean_tok = token.strip(" ,.;:!?")
                    if len(clean_tok) >= 4 and any(ch.isdigit() for ch in clean_tok):
                        target_id = clean_tok
                        break
            if not target_id:
                target_id = q_clean
            try:
                inv_data = self.get_invoice_download(target_id, customer_phone)
                reply = (
                    f"🧾 *टॅक्स इनव्हॉइस (Tax Invoice) - #{inv_data.invoice_number}*\n\n"
                    f"• **ऑर्डर क्रमांक:** #{inv_data.order_number}\n"
                    f"• **एकूण रक्कम:** ₹{inv_data.total_amount:,.2f}\n"
                    f"• **दिनांक:** {inv_data.date.strftime('%d %b %Y')}\n\n"
                    f"📄 **थेट PDF डाऊनलोड करण्यासाठी खालील लिंकवर क्लिक करा:**\n"
                    f"👉 [Download Tax Invoice PDF]({inv_data.download_link})"
                )
                speech = f"आपले बिल क्रमांक {inv_data.invoice_number} तयार आहे. आपण लिंकवरून PDF डाऊनलोड करू शकता."
                return CustomerSupportQueryResponse(
                    intent="invoice_download",
                    reply=reply,
                    speech_text=speech,
                    data=inv_data.model_dump(),
                    suggested_actions=["Download PDF", "Track Order", "Return Item"],
                )
            except Exception:
                reply = (
                    f"आपले इनव्हॉइस शोधण्यासाठी कृपया आपला **बिल क्रमांक** (उदा. *INV-1001*) "
                    f"किंवा **ऑर्डर क्रमांक** सांगा."
                )
                return CustomerSupportQueryResponse(
                    intent="invoice_download",
                    reply=reply,
                    speech_text="कृपया आपला बिल क्रमांक किंवा ऑर्डर क्रमांक सांगा.",
                    suggested_actions=["Find bill by phone number", "Contact Cashier"],
                )

        # ---------------------------------------------------------
        # C. INTENT: RETURN / EXCHANGE REQUEST
        # ---------------------------------------------------------
        return_keywords = ["return", "रिटर्न", "बदलून", "exchange", "खराब", "तक्रार", "damage", "faulty", "परत"]
        if any(k in q_lower for k in return_keywords):
            if extracted_ord and customer_phone:
                try:
                    ret_res = self.initiate_customer_return(
                        order_number=extracted_ord,
                        customer_phone=customer_phone,
                        reason=q_clean,
                        refund_preference="store_credit",
                    )
                    reply = (
                        f"🔄 *रिटर्न रिक्वेस्ट नोंदवली गेली (Return Initiated)*\n\n"
                        f"• **रिटर्न कोड:** *#{ret_res.return_number}*\n"
                        f"• **ऑर्डर क्रमांक:** #{ret_res.order_number}\n"
                        f"• **अपेक्षित परतावा रक्कम:** ₹{ret_res.total_refund_amount:,.2f}\n"
                        f"• **रिफंड मोड:** {ret_res.refund_preference.title()}\n\n"
                        f"आमची सपोर्ट टीम लवकरच वस्तूची पडताळणी करून रिफंड किंवा स्टोअर क्रेडिट जमा करेल. धन्यवाद! 🙏"
                    )
                    speech = f"आपली रिटर्न विनंती नोंदवली असून रिटर्न क्रमांक {ret_res.return_number} आहे."
                    return CustomerSupportQueryResponse(
                        intent="return_request",
                        reply=reply,
                        speech_text=speech,
                        data=ret_res.model_dump(),
                        suggested_actions=["Check return status", "Store return policy"],
                    )
                except Exception as exc:
                    reply = f"⚠️ रिटर्न विनंतीमध्ये अडचण: {exc}"
                    return CustomerSupportQueryResponse(
                        intent="return_request",
                        reply=reply,
                        speech_text=str(exc),
                        suggested_actions=["Contact Store Manager", "View return policy"],
                    )

            reply = (
                f"🔄 *वस्तू परत किंवा बदलून हवी आहे का?*\n\n"
                f"Retail-OS मध्ये खरेदीच्या **१४ दिवसांच्या आत** सहज रिटर्न सुविधा उपलब्ध आहे.\n"
                f"रिटर्न रिक्वेस्ट सुरू करण्यासाठी खालीलप्रमाणे मेसेज करा:\n"
                f"👉 *'रिटर्न ऑर्डर ORD-1001 [मोबाईल नंबर] [कारणे]'*\n\n"
                f"किंवा थेट खालील बटणावर क्लिक करा."
            )
            return CustomerSupportQueryResponse(
                intent="return_request",
                reply=reply,
                speech_text="वस्तू रिटर्न करण्यासाठी कृपया आपला ऑर्डर क्रमांक आणि मोबाईल नंबर सांगा.",
                suggested_actions=["Initiate Return Request", "Read Return Policy", "Contact Support"],
            )

        # ---------------------------------------------------------
        # D. INTENT: STORE FAQ & INFORMATION
        # ---------------------------------------------------------
        faq_keywords = [
            "पत्ता", "address", "वेळ", "timing", "hours", "कधी चालू", "उघडे", "open",
            "phone", "फोन", "नंबर", "संपर्क", "contact", "location", "कुठे आहे दुकान",
        ]
        if any(k in q_lower for k in faq_keywords):
            faq = self.get_store_faq()
            reply = (
                f"🏪 *{faq['store_name']} - माहिती व संपर्क*\n\n"
                f"• 📍 **पत्ता:** {faq['address']}\n"
                f"• ⏰ **दुकान वेळ:** {faq['operating_hours']}\n"
                f"• 📞 **फोन / WhatsApp:** {faq['phone']}\n"
                f"• 💳 **पेमेंट पर्याय:** {faq['payment_methods']}\n"
                f"• 🚚 **WhatsApp घरपोच ऑर्डर:** {faq['whatsapp_ordering']}\n"
                f"• 🔄 **रिटर्न पॉलिसी:** {faq['return_policy']}"
            )
            speech = f"{faq['store_name']} चे दुकान रोज सकाळी ८ ते रात्री १० पर्यंत उघडे असते. पत्ता {faq['address']} असा आहे."
            return CustomerSupportQueryResponse(
                intent="faq_store_info",
                reply=reply,
                speech_text=speech,
                data=faq,
                suggested_actions=["Track an order", "Order on WhatsApp", "Get Directions"],
            )

        # ---------------------------------------------------------
        # E. GREETINGS & DEFAULT HELPFUL ASSISTANT
        # ---------------------------------------------------------
        greeting_words = ["hi", "hello", "namaste", "namaskar", "नमस्कार", "नमस्ते", "हेल्प", "help"]
        if any(w in q_lower for w in greeting_words) or len(q_clean) < 4:
            reply = (
                f"🙏 *नमस्कार! मी {store_name} चा 24/7 AI ग्राहक सहाय्यक (Customer Support Bot) आहे.*\n\n"
                f"मी तुम्हाला पुढील गोष्टींमध्ये मदत करू शकतो:\n"
                f"1. 📦 **ऑर्डर ट्रॅक करा** (उदा. *'माझी ऑर्डर ORD-1001 कुठे आहे?'*)\n"
                f"2. 🧾 **बिल / इनव्हॉइस मिळवा** (उदा. *'माझे बिल डाऊनलोड करायचे आहे'*)\n"
                f"3. 🔄 **रिटर्न किंवा एक्सचेंज विनंती** (उदा. *'ऑर्डर रिटर्न करायची आहे'*)\n"
                f"4. 🏪 **दुकान वेळ व पत्ता माहिती** (उदा. *'दुकान कधी उघडे असते?'*)\n\n"
                f"आपला प्रश्न खाली टाईप करा किंवा सुचवलेले पर्याय निवडा! ✨"
            )
            speech = f"नमस्कार! मी {store_name} चा सहाय्यक आहे. मी ऑर्डर ट्रॅक करणे, बिल देणे किंवा रिटर्न करण्यास मदत करू शकतो."
            actions = ["Track Order", "Download Tax Invoice", "Return / Exchange Item", "Store Timings & Address"]
            return CustomerSupportQueryResponse(
                intent="greeting",
                reply=reply,
                speech_text=speech,
                suggested_actions=actions,
            )

        # General inquiry fallback
        reply = (
            f"धन्यवाद! आपल्या प्रश्नाबाबत मी अधिक माहिती शोधत आहे. "
            f"आपण खालील पर्यायांपैकी एकावर क्लिक करून थेट माहिती मिळवू शकता किंवा दुकानाच्या सपोर्ट टीमशी `{store.phone if store else 'संपर्क'}` वर संपर्क करू शकता."
        )
        return CustomerSupportQueryResponse(
            intent="general",
            reply=reply,
            speech_text=reply,
            suggested_actions=["Track Order", "Download Tax Invoice", "Store Information", "Contact Store Manager"],
        )

    def _get_status_description(
        self, order_status: str, delivery_status: Optional[str], eta: Optional[str]
    ) -> str:
        s = order_status.lower()
        if s in ["confirmed", "processing"]:
            return "आपली ऑर्डर दुकानात पॅक केली जात आहे (Packing in Progress)."
        elif s in ["dispatched", "out_for_delivery"] or delivery_status == "out_for_delivery":
            return f"आपली ऑर्डर डिलिव्हरीसाठी बाहेर पडली आहे (Out for Delivery). {f'अंदाजे वेळ: {eta}' if eta else ''}"
        elif s in ["delivered", "completed"] or delivery_status == "delivered":
            return "आपली ऑर्डर यशस्वीरीत्या पोहोचवली गेली आहे (Delivered). खरेदीबद्दल धन्यवाद!"
        elif s == "cancelled":
            return "ही ऑर्डर रद्द करण्यात आली आहे (Cancelled)."
        return f"ऑर्डर स्थिती: {order_status.title()}."


def func_upper_order(clean_ord: str):
    from sqlalchemy import func
    return func.upper(Order.order_number) == clean_ord
