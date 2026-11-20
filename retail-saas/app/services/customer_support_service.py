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
from app.models.coupon import Coupon
from app.models.customer import Customer
from app.models.delivery import Delivery
from app.models.delivery_method import DeliveryMethod
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_return import OrderReturn, OrderReturnItem
from app.models.product import Product
from app.models.store import Store
from app.models.storefront_setting import StorefrontSetting
from app.models.tenant import Tenant
from app.models.whatsapp import WhatsAppSetting
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

    def _resolve_context(self) -> Tuple[Optional[Tenant], Optional[Store]]:
        store = None
        if self.store_id:
            store = self.db.query(Store).filter(Store.id == self.store_id).first()
            if store:
                tenant = self.db.query(Tenant).filter(Tenant.id == store.tenant_id).first()
                self.tenant_id = store.tenant_id
                return tenant, store

        if self.tenant_id and self.tenant_id != 1:
            tenant = self.db.query(Tenant).filter(Tenant.id == self.tenant_id).first()
            if tenant:
                store = (
                    self.db.query(Store)
                    .filter(Store.tenant_id == self.tenant_id, Store.is_active.is_(True))
                    .order_by(Store.is_main.desc(), Store.id.asc())
                    .first()
                )
                if store:
                    return tenant, store

        # Fallback to the primary active store across the DB
        store = (
            self.db.query(Store)
            .filter(Store.is_active.is_(True))
            .order_by(Store.is_main.desc(), Store.id.asc())
            .first()
        )
        tenant = None
        if store:
            self.store_id = store.id
            self.tenant_id = store.tenant_id
            tenant = self.db.query(Tenant).filter(Tenant.id == store.tenant_id).first()
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
        """Provides dynamic store facts: address, timings, payment modes, contact directly from database."""
        tenant, store = self._resolve_context()
        s_name = store.name if store and store.name else (tenant.name if tenant and tenant.name else "स्टोअर")
        s_city = store.city if store and store.city else ""
        s_phone = store.phone if store and store.phone else ""
        s_email = store.email if store and store.email else ""

        # Build address dynamically from available DB fields only
        addr_components = [part for part in [store.address, store.city, store.state, store.pincode] if store and part]
        full_addr = ", ".join(addr_components) if addr_components else (s_name if s_name else "पत्ता नोंदवलेला नाही")

        # Check tenant settings for business hours
        hours_val = "कामाच्या वेळेबाबत अचूक माहितीसाठी कृपया थेट शाखेशी संपर्क करा."
        if tenant and tenant.settings and isinstance(tenant.settings, dict):
            if tenant.settings.get("operating_hours"):
                hours_val = tenant.settings.get("operating_hours")
            elif tenant.settings.get("business_hours"):
                hours_val = tenant.settings.get("business_hours")

        # Payment modes from database settings
        wa = self.db.query(WhatsAppSetting).filter(WhatsAppSetting.tenant_id == self.tenant_id).first() if self.tenant_id else None
        pay_modes = ["UPI (QR स्कॅन)", "Cash on Delivery (रोख रक्कम)", "क्रेडिट / डेबिट कार्ड्स"]
        if wa and wa.upi_vpa:
            pay_modes[0] = f"UPI ({wa.upi_vpa})"

        # WhatsApp ordering text
        if s_phone:
            wa_text = f"होय! आपण {s_phone} या नंबरवर किराणा यादी पाठवून ऑर्डर करू शकता."
        else:
            wa_text = "WhatsApp नंबर नोंदवलेला नाही. थेट दुकानातून किंवा ऑनलाइन खरेदी करू शकता."

        # Return policy from StorefrontSetting or default policy
        sf = self.db.query(StorefrontSetting).filter(StorefrontSetting.tenant_id == self.tenant_id).first() if self.tenant_id else None
        ret_policy = sf.return_policy if (sf and sf.return_policy) else "खरेदीच्या १४ दिवसांच्या आत बिल पावतीसह सहज रिटर्न किंवा एक्सचेंज सुविधा उपलब्ध आहे."

        return {
            "store_id": store.id if store else self.store_id,
            "tenant_id": store.tenant_id if store else self.tenant_id,
            "store_name": s_name,
            "address": full_addr,
            "city": s_city or "उपलब्ध नाही",
            "phone": s_phone or "उपलब्ध नाही",
            "email": s_email or "उपलब्ध नाही",
            "operating_hours": hours_val,
            "payment_methods": ", ".join(pay_modes),
            "whatsapp_ordering": wa_text,
            "return_policy": ret_policy,
        }

    # --------------------------------------------------------------------------
    # 5. NATURAL LANGUAGE AI DISPATCHER (MARATHI / HINDI / ENGLISH / HINGLISH)
    # --------------------------------------------------------------------------

    def _call_gemini_support(self, query_str: str, store_info: dict, language: str = "mr") -> Optional[CustomerSupportQueryResponse]:
        api_key = getattr(settings, "GEMINI_API_KEY", "")
        if not api_key:
            return None

        import urllib.request
        import urllib.error

        system_instruction = (
            "You are Retail-OS AI Customer Care Bot (२४/७ AI ग्राहक सेवा प्रतिनिधी), a helpful and polite virtual assistant for a retail store.\n"
            "Rules:\n"
            "1. Language Matching: Answer in the same language or dialect the user asked (Marathi, Hindi, English, or Roman Marathi / Hinglish).\n"
            "2. Ground your answer strictly in the provided Store Info:\n"
            f"   - Store Name: {store_info.get('store_name')}\n"
            f"   - Address: {store_info.get('address')}\n"
            f"   - Phone: {store_info.get('phone')}\n"
            f"   - Hours: {store_info.get('operating_hours')}\n"
            f"   - Payment Options: {store_info.get('payment_methods')}\n"
            "3. Do not invent fake discounts, phone numbers, or addresses. If information is not provided, advise the user to contact the store directly.\n"
            "4. Return strict JSON with: {\"intent\": \"general\", \"reply\": \"markdown answer with emojis and formatting\", \"speech_text\": \"clean plain spoken text for speaker without asterisks\", \"suggested_actions\": [\"Action 1\", \"Action 2\"]}"
        )
        url = f"{settings.GEMINI_API_URL}/models/{getattr(settings, 'GEMINI_MODEL', 'gemini-1.5-flash')}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": query_str}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                text_content = res_data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_content)
                return CustomerSupportQueryResponse(
                    intent=parsed.get("intent", "general"),
                    reply=parsed.get("reply", "मी आपली कशी मदत करू?"),
                    speech_text=parsed.get("speech_text"),
                    suggested_actions=parsed.get("suggested_actions", ["Track Order", "Store Timings & Address"]),
                )
        except Exception as e:
            logger.info("Gemini support call failed or skipped: %s", e)
            return None

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
        store_name = store.name if store and store.name else (tenant.name if tenant and tenant.name else "स्टोअर")
        store_phone = store.phone if store and store.phone else None
        store_addr = store.address if store and store.address else None
        store_city = store.city if store and store.city else None

        # Check if customer typed a phone number in the query
        digits_only = re.sub(r"\D", "", q_clean)
        if len(digits_only) == 10:
            customer_phone = digits_only
        elif len(digits_only) == 12 and digits_only.startswith("91"):
            customer_phone = digits_only[2:]

        # Extract explicit order or invoice number if typed in query (e.g. ORD-1001, ORD-SUPP-12345, INV-1001)
        extracted_ord = order_number
        if not extracted_ord:
            ord_match = re.search(r"\b((?:ORD|INV)[-_A-Z0-9]+)\b", q_clean, re.IGNORECASE)
            if ord_match:
                extracted_ord = ord_match.group(1).upper()

        q_lower = q_clean.lower()

        # 1. Dynamically resolve specific store from Order or Phone
        if extracted_ord:
            clean_ord = extracted_ord.strip().upper()
            ord_obj = self.db.query(Order).filter(func_upper_order(clean_ord)).first()
            if ord_obj and ord_obj.store_id:
                ord_store = self.db.query(Store).filter(Store.id == ord_obj.store_id).first()
                if ord_store:
                    store = ord_store
                    self.store_id = ord_store.id
                    self.tenant_id = ord_store.tenant_id
                    tenant = self.db.query(Tenant).filter(Tenant.id == ord_store.tenant_id).first()
                    store_name = ord_store.name
                    store_phone = ord_store.phone or store_phone
                    store_addr = ord_store.address or store_addr
                    store_city = ord_store.city or store_city
        elif customer_phone and customer_phone.strip():
            raw_ph = re.sub(r"\D", "", customer_phone.strip())
            short_ph = raw_ph[-10:] if len(raw_ph) >= 10 else raw_ph
            cust_candidates = self.db.query(Customer.id).filter(
                (Customer.phone == raw_ph) | 
                (Customer.phone == short_ph) | 
                (Customer.phone.like(f"%{short_ph}"))
            ).all()
            cust_ids = [c[0] for c in cust_candidates]
            if cust_ids:
                last_ord = (
                    self.db.query(Order)
                    .filter(Order.customer_id.in_(cust_ids))
                    .order_by(Order.created_at.desc())
                    .first()
                )
                if last_ord and last_ord.store_id:
                    ord_store = self.db.query(Store).filter(Store.id == last_ord.store_id).first()
                    if ord_store:
                        store = ord_store
                        self.store_id = ord_store.id
                        self.tenant_id = ord_store.tenant_id
                        tenant = self.db.query(Tenant).filter(Tenant.id == ord_store.tenant_id).first()
                        store_name = ord_store.name
                        store_phone = ord_store.phone or store_phone
                        store_addr = ord_store.address or store_addr
                        store_city = ord_store.city or store_city

        # 2. Check if customer specifically mentions a city, code, or branch in their message
        for s in self.db.query(Store).filter(Store.is_active.is_(True)).all():
            if (
                (s.name and s.name.lower() in q_lower) or
                (s.code and s.code.lower() in q_lower) or
                (s.city and s.city.lower() in q_lower)
            ):
                store = s
                self.store_id = s.id
                self.tenant_id = s.tenant_id
                tenant = self.db.query(Tenant).filter(Tenant.id == s.tenant_id).first()
                store_name = s.name
                store_phone = s.phone or store_phone
                store_addr = s.address or store_addr
                store_city = s.city or store_city
                break

        # ---------------------------------------------------------
        # PRIORITY 1: PURE PHONE NUMBER ENTERED IN CHAT (e.g. '9960106127')
        # ---------------------------------------------------------
        if customer_phone and (len(re.sub(r"[\s+\-()]", "", q_clean)) in [10, 11, 12, 13] or q_clean == customer_phone):
            phone_val = customer_phone
            clean_digits = re.sub(r"\D", "", phone_val)
            short_digits = clean_digits[-10:] if len(clean_digits) >= 10 else clean_digits

            cust_records = self.db.query(Customer).filter(
                (Customer.phone == clean_digits) | 
                (Customer.phone == short_digits) | 
                (Customer.phone.like(f"%{short_digits}"))
            ).all()
            cust_ids = [c.id for c in cust_records]

            cust_orders = []
            if cust_ids:
                cust_orders = self.db.query(Order).filter(Order.customer_id.in_(cust_ids)).order_by(Order.created_at.desc()).all()
            
            if cust_orders:
                latest = cust_orders[0]
                if latest.store_id:
                    ord_store = self.db.query(Store).filter(Store.id == latest.store_id).first()
                    if ord_store:
                        store = ord_store
                        self.store_id = ord_store.id
                        self.tenant_id = ord_store.tenant_id
                        store_name = ord_store.name
                        store_phone = ord_store.phone or store_phone

                track_data = self.track_order(latest.order_number, phone_val)
                reply = (
                    f"📱 *मोबाईल नंबर {phone_val} शी जोडलेली शेवटची ऑर्डर आढळली:*\n\n"
                    f"📦 *ऑर्डर क्रमांक:* **#{track_data.order_number}**\n"
                    f"• 🏪 **स्टोअर:** {store_name}\n"
                    f"• **सध्याची स्थिती:** *{track_data.status.upper()}*\n"
                    f"• **तपशील:** {track_data.status_description}\n"
                    f"• **एकूण रक्कम:** ₹{track_data.total_amount:,.2f}\n"
                    f"• **ऑर्डर दिनांक:** {track_data.order_date.strftime('%d %b %Y, %I:%M %p')}\n"
                )
                if track_data.delivery_partner:
                    reply += f"• **डिलिव्हरी पार्टनर:** {track_data.delivery_partner}\n"
                if track_data.estimated_delivery:
                    reply += f"• **अंदाजे वेळ:** {track_data.estimated_delivery}\n"
                
                track_dict = track_data.model_dump()
                track_dict["store_id"] = latest.store_id
                track_dict["store_name"] = store_name

                return CustomerSupportQueryResponse(
                    intent="order_tracking",
                    reply=reply,
                    speech_text=f"आपल्या {phone_val} नंबरवरील {store_name} ची ऑर्डर {track_data.order_number} सध्या {track_data.status} स्थितीत आहे.",
                    data=track_dict,
                    suggested_actions=["जीएसटी बिल डाऊनलोड", "वस्तू रिटर्न व रिफंड", "WhatsApp वरून किराणा ऑर्डर"],
                )
            else:
                order_help = f"🛒 **नवीन किराणा माल मागवण्यासाठी ({store_name}):**\n"
                if store_phone:
                    order_help += f"• आपण थेट आमच्या **`{store_phone}`** या अधिकृत WhatsApp नंबरवर किराणा यादी पाठवून घरपोच माल मागवू शकता.\n"
                else:
                    order_help += f"• आपण थेट {store_name} शाखेला भेट देऊन किंवा ऑनलाइन ऑर्डर करू शकता.\n"
                order_help += "• किंवा जर आपल्याकडे आधीचा ऑर्डर नंबर असेल तर तो इथे टाईप करा (उदा. *ORD-1001*)."

                reply = (
                    f"📱 *मोबाईल नंबर नोंदवला गेला: {phone_val}*\n\n"
                    f"या नंबरवर सध्या कोणतीही सक्रिय ऑनलाइन ऑर्डर सापडली नाही.\n\n"
                    f"{order_help}"
                )
                return CustomerSupportQueryResponse(
                    intent="order_tracking",
                    reply=reply,
                    speech_text=f"आपल्या {phone_val} नंबरवर कोणतीही चालू ऑर्डर सापडली नाही.",
                    data={"phone": phone_val, "store_id": store.id if store else self.store_id, "store_name": store_name},
                    suggested_actions=["saman order karaycha ahe", "WhatsApp वरून किराणा ऑर्डर", "दुकान वेळ व पत्ता", "मॅनेजरशी बोला"],
                )

        # ---------------------------------------------------------
        # PRIORITY 2: HOW TO ORDER / PLACE ORDER (SAMAN, GROCERY, BOOKING)
        # ---------------------------------------------------------
        new_order_keywords = [
            "saman order", "order karaych", "order karaycha", "order kashi", "order kasa",
            "kashi book", "kasa book", "online order", "नवीन ऑर्डर", "ऑर्डर कशी करायची",
            "ऑर्डर करायची", "माल मागवायचा", "सामान मागवायचे", "किराणा ऑर्डर", "kirana order",
            "माल कसा मागवायचा", "कशी मागवायची", "order book", "booking", "बुक कशी", "बुक करू",
            "order dyaychi", "order deychi", "खरेदी कशी", "saman pahije", "kirana pahije", "mal pahije",
            "whatsapp varun", "whatsapp वरून", "चिठ्ठी", "किराणा यादी", "saman kharedi", "mal kharedi"
        ]
        if any(k in q_lower for k in new_order_keywords) and not any(k in q_lower for k in ["track", "status", "कुठे आहे", "kuthe", "कधी येईल", "पोहोचली"]):
            methods = []
            if store_phone:
                methods.append(
                    f"1. 💬 **WhatsApp द्वारे थेट ऑर्डर:**\n"
                    f"   • कागदावर किराणा सामानाची यादी लिहा किंवा मेसेज टाईप करा.\n"
                    f"   • ती यादी थेट आमच्या **`{store_phone}`** या अधिकृत WhatsApp नंबरवर पाठवा.\n"
                    f"   • आमचा प्रतिनिधी आपले बिल पाठवून माल पोहोचवण्याची व्यवस्था करेल!"
                )
            methods.append(
                f"2. 🌐 **ऑनलाइन स्टोअरफ्रंटवरून:**\n"
                f"   • आमच्या कॅटलॉगमधून वस्तू निवडून थेट कार्टमध्ये ॲड करा आणि ऑर्डर पूर्ण करा."
            )
            methods.append(
                f"3. 🏪 **थेट दुकानाला भेट देऊन:**\n"
                f"   • {store_name} शाखेत स्वतः येऊन खात्रीशीर खरेदी करू शकता."
            )
            reply = (
                f"🛒 *किराणा व माल ऑर्डर कसा करावा? ({store_name})*\n\n"
                + "\n\n".join(methods)
                + "\n\n💡 आपण आधी ऑर्डर केली असल्यास थेट **ऑर्डर नंबर** किंवा **फोन नंबर** पाठवून स्टेटस ट्रॅक करू शकता!"
            )
            return CustomerSupportQueryResponse(
                intent="faq_store_info",
                reply=reply,
                speech_text=f"{store_name} मध्ये WhatsApp द्वारे, ऑनलाइन किंवा थेट दुकानातून खरेदी करता येते.",
                data={"whatsapp_number": store_phone, "store_name": store_name},
                suggested_actions=["WhatsApp वरून किराणा ऑर्डर", "घरपोच डिलिव्हरी माहिती", "पेमेंट पर्याय", "दुकान वेळ व पत्ता"],
            )

        # ---------------------------------------------------------
        # PRIORITY 3: INTENT: ORDER TRACKING (Specific Tracking Requests)
        # ---------------------------------------------------------
        track_keywords = [
            "track", "status", "कुठे आहे", "कधी येईल", "कधी मिळणार", "पोहोचली",
            "पार्सल", "delivery status", "order status", "where is my order",
            "kuthe", "kadhi yeil", "order kuthe", "order kadhi", "पार्सल कुठे",
            "माझी ऑर्डर", "माझे पार्सल", "order chi mahiti"
        ]
        if (any(k in q_lower for k in track_keywords) or extracted_ord) and not any(k in q_lower for k in ["return", "रिटर्न", "बिल", "invoice"]):
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

                    actions = ["जीएसटी बिल डाऊनलोड", "वस्तू रिटर्न व रिफंड", "मॅनेजरशी बोला"]
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
                suggested_actions=["saman order karaycha ahe", "WhatsApp वरून किराणा ऑर्डर", "दुकान वेळ व पत्ता"],
            )

        # ---------------------------------------------------------
        # PRIORITY 4: INTENT: INVOICE / BILL DOWNLOAD
        # ---------------------------------------------------------
        bill_keywords = ["bill", "invoice", "पावती", "बिल", "पावती हवी", "tax invoice", "receipt", "रसीद", "bill dya", "bill pahije", "bill download"]
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
                    suggested_actions=["Download PDF", "ऑर्डर ट्रॅक करा", "वस्तू रिटर्न व रिफंड"],
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
                    suggested_actions=["फोन नंबरने बिल शोधा", "मॅनेजरशी बोला", "दुकान वेळ व पत्ता"],
                )

        # ---------------------------------------------------------
        # PRIORITY 5: INTENT: RETURN / EXCHANGE REQUEST
        # ---------------------------------------------------------
        return_keywords = ["return", "रिटर्न", "बदलून", "exchange", "खराब", "तक्रार", "damage", "faulty", "परत", "return karaych", "vapas"]
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
                        suggested_actions=["रिटर्न स्थिती तपासा", "रिटर्न पॉलिसी", "मॅनेजरशी बोला"],
                    )
                except Exception as exc:
                    reply = f"⚠️ रिटर्न विनंतीमध्ये अडचण: {exc}"
                    return CustomerSupportQueryResponse(
                        intent="return_request",
                        reply=reply,
                        speech_text=str(exc),
                        suggested_actions=["मॅनेजरशी बोला", "रिटर्न पॉलिसी"],
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
                suggested_actions=["ऑर्डर ट्रॅक करा", "दुकान वेळ व पत्ता", "मॅनेजरशी बोला"],
            )

        # ---------------------------------------------------------
        # PRIORITY 6: INTENT: ALL STORES LIST
        # ---------------------------------------------------------
        all_store_keywords = ["सर्व शाखा", "सर्व दुकान", "सर्व स्टोअर", "दुकानांची यादी", "all stores", "branches", "इतर शाखा", "इतर दुकान"]
        if any(k in q_lower for k in all_store_keywords):
            all_stores = self.db.query(Store).filter(Store.is_active.is_(True)).order_by(Store.is_main.desc(), Store.id.asc()).all()
            lines = []
            for idx, s in enumerate(all_stores[:10], 1):
                b_type = "सेंट्रल वेअरहाउस" if s.is_warehouse else ("मुख्य स्टोअर" if s.is_main else "रिटेल शाखा")
                s_phone_disp = s.phone if s.phone else "नोंदवलेला नाही"
                s_addr_disp = s.address if s.address else (s.city if s.city else "पत्ता नोंदवलेला नाही")
                lines.append(f"{idx}. 🏪 **{s.name}**" + (f" ({s.city})" if s.city else "") + f"\n   • 📍 पत्ता: {s_addr_disp}\n   • 📞 फोन: `{s_phone_disp}`\n   • 🏢 प्रकार: {b_type}")
            reply = (
                f"🏢 *आमच्या सर्व शाखांची यादी (एकूण {len(all_stores)})*\n\n"
                + "\n\n".join(lines)
                + "\n\n💡 आपण कोणत्याही शाखेचा पत्ता, वेळ किंवा ऑर्डरबद्दल थेट विचारू शकता किंवा खालील बटणावर क्लिक करा!"
            )
            store_actions = [s.name for s in all_stores[:6]]
            return CustomerSupportQueryResponse(
                intent="faq_store_info",
                reply=reply,
                speech_text=f"आमच्याकडे एकूण {len(all_stores)} शाखा उपलब्ध आहेत.",
                data={"stores": [{"id": s.id, "name": s.name, "city": s.city, "phone": s.phone} for s in all_stores]},
                suggested_actions=store_actions + ["ऑर्डर ट्रॅक करा", "WhatsApp वरून किराणा ऑर्डर"],
            )

        # ---------------------------------------------------------
        # PRIORITY 7: INTENT: DELIVERY / HOME DELIVERY INFO
        # ---------------------------------------------------------
        delivery_keywords = ["होम डिलिव्हरी", "home delivery", "घरपोच", "डिलिव्हरी शुल्क", "delivery charges", "किती वेळात डिलिव्हरी", "डिलिव्हरी"]
        if any(k in q_lower for k in delivery_keywords):
            del_methods = (
                self.db.query(DeliveryMethod)
                .filter(DeliveryMethod.tenant_id == self.tenant_id, DeliveryMethod.is_active.is_(True))
                .all()
            )
            if del_methods:
                lines = []
                for dm in del_methods:
                    charge_str = f"₹{dm.base_charge}" if dm.base_charge else "मोफत"
                    lines.append(f"• 🚚 **{dm.name}:** दर: {charge_str} | अंदाजे वेळ: {dm.estimated_days or 1} दिवस")
                reply = (
                    f"🛵 *घरपोच डिलिव्हरी पर्याय ({store_name})*\n\n"
                    + "\n".join(lines)
                    + (f"\n\n📲 **अधिक माहितीसाठी:** `{store_phone}` वर संपर्क करा." if store_phone else "")
                )
            else:
                sf = self.db.query(StorefrontSetting).filter(StorefrontSetting.tenant_id == self.tenant_id).first()
                if sf and sf.shipping_policy:
                    reply = f"🛵 *घरपोच डिलिव्हरी माहिती ({store_name})*\n\n{sf.shipping_policy}"
                else:
                    contact_hint = f"`{store_phone}` या नंबरवर संपर्क करा." if store_phone else "दुकानाला थेट भेट द्या किंवा संपर्क करा."
                    reply = (
                        f"🛵 *घरपोच डिलिव्हरी माहिती ({store_name})*\n\n"
                        f"डिलिव्हरी सेवा, क्षेत्र आणि शुल्काबाबत तपशीलवार माहितीसाठी कृपया {contact_hint}"
                    )
            return CustomerSupportQueryResponse(
                intent="faq_store_info",
                reply=reply,
                speech_text=f"{store_name} डिलिव्हरी माहिती उपलब्ध आहे.",
                data={"store_name": store_name},
                suggested_actions=["WhatsApp वरून किराणा ऑर्डर", "पेमेंट पर्याय", "दुकान वेळ व पत्ता"],
            )

        # ---------------------------------------------------------
        # PRIORITY 8: INTENT: PAYMENT MODES
        # ---------------------------------------------------------
        pay_keywords = ["पेमेंट पर्याय", "payment modes", "payment options", "कसे पैसे", "कार्ड चालते का", "gpay", "phonepe", "उधारी मिळते का", "पेमेंट"]
        if any(k in q_lower for k in pay_keywords):
            wa = self.db.query(WhatsAppSetting).filter(WhatsAppSetting.tenant_id == self.tenant_id).first() if self.tenant_id else None
            pay_lines = [
                "• 💵 **Cash on Delivery (COD):** माल मिळाल्यावर रोख पैसे देऊ शकता.",
                "• 💳 **क्रेडिट / डेबिट कार्ड्स:** सर्व प्रमुख बँकांची कार्ड्स स्वीकारली जातात."
            ]
            if wa and wa.upi_vpa:
                pay_lines.insert(0, f"• 📱 **UPI:** QR कोड स्कॅन करून किंवा `{wa.upi_vpa}` द्वारे थेट पेमेंट.")
            else:
                pay_lines.insert(0, "• 📱 **UPI:** Google Pay, PhonePe, Paytm द्वारे थेट पेमेंट.")
            
            if wa and wa.ai_khata_reminders_enabled:
                pay_lines.append("• 📓 **खाते / Store Credit:** नियमित ग्राहकांसाठी उधारी खाते सुविधा.")

            reply = (
                f"💳 *उपलब्ध पेमेंट पर्याय ({store_name})*\n\n"
                + "\n".join(pay_lines)
            )
            return CustomerSupportQueryResponse(
                intent="faq_store_info",
                reply=reply,
                speech_text=f"{store_name} मध्ये UPI, कॅश आणि कार्ड पेमेंट स्वीकारले जाते.",
                data={"payment_modes": ["UPI", "Cash", "Cards"]},
                suggested_actions=["ऑर्डर ट्रॅक करा", "WhatsApp वरून किराणा ऑर्डर", "दुकान वेळ व पत्ता"],
            )

        # ---------------------------------------------------------
        # PRIORITY 9: INTENT: OFFERS & DISCOUNTS
        # ---------------------------------------------------------
        offer_keywords = ["offer", "offers", "discount", "सवलत", "ऑफर", "स्कीम", "किंमत कमी"]
        if any(k in q_lower for k in offer_keywords):
            active_coupons = (
                self.db.query(Coupon)
                .filter(Coupon.tenant_id == self.tenant_id, Coupon.is_active.is_(True))
                .all()
            )
            if active_coupons:
                coupon_lines = []
                for c in active_coupons:
                    disc_str = f"{c.discount_value}% सूट" if c.discount_type == "percentage" else f"₹{c.discount_value} सूट"
                    min_str = f" (किमान खरेदी: ₹{c.min_order_amount})" if c.min_order_amount else ""
                    coupon_lines.append(f"• 🏷️ **कूपन कोड:** `{c.code}` — **{disc_str}**{min_str}\n   {c.description or ''}")
                reply = (
                    f"🎁 *आजच्या चालू ऑफर्स व सवलती ({store_name})*\n\n"
                    + "\n".join(coupon_lines)
                    + "\n\n💡 खरेदी करताना वरील कूपन कोड वापरून आपण सवलत मिळवू शकता!"
                )
                coupon_data = [{"code": c.code, "discount": float(c.discount_value)} for c in active_coupons]
            else:
                reply = (
                    f"🎁 *सवलती व ऑफर्स ({store_name})*\n\n"
                    f"सध्या {store_name} मध्ये कोणतीही सक्रिय कूपन ऑफर किंवा डिस्काउंट स्कीम उपलब्ध नाही.\n"
                    f"नवीन ऑफर्स सुरू झाल्यावर आम्ही नक्की कळवू!"
                )
                coupon_data = []

            return CustomerSupportQueryResponse(
                intent="faq_store_info",
                reply=reply,
                speech_text=f"{store_name} च्या चालू ऑफर्सची माहिती.",
                data={"offers": coupon_data},
                suggested_actions=["WhatsApp वरून किराणा ऑर्डर", "सर्व शाखांची माहिती", "दुकान वेळ व पत्ता"],
            )

        # ---------------------------------------------------------
        # PRIORITY 10: INTENT: CONTACT STORE MANAGER
        # ---------------------------------------------------------
        manager_keywords = ["मॅनेजर", "manager", "helpline", "कॉल करायचा", "मदतनीस", "थेट बोलायचे", "हेल्पलाईन"]
        if any(k in q_lower for k in manager_keywords):
            lines = [f"• 🏪 **शाखा:** {store_name}"]
            if store_addr:
                lines.append(f"• 📍 **पत्ता:** {store_addr}" + (f", {store_city}" if store_city and store_city not in store_addr else ""))
            if store_phone:
                lines.append(f"• 📱 **मॅनेजर थेट फोन / WhatsApp:** `{store_phone}`")
            else:
                lines.append("• 📱 **फोन नंबर:** नोंदवलेला नाही (कृपया दुकानाला थेट भेट द्या)")
            if store and store.email:
                lines.append(f"• ✉️ **ईमेल:** `{store.email}`")
            
            reply = (
                f"📞 *स्टोअर व्यवस्थापन संपर्क ({store_name})*\n\n"
                + "\n".join(lines)
                + "\n\n💡 विशेष सहाय्य किंवा चौकशीसाठी आपण थेट संपर्क करू शकता."
            )
            return CustomerSupportQueryResponse(
                intent="human_handoff",
                reply=reply,
                speech_text=f"आपण {store_name} व्यवस्थापकाशी संपर्क करू शकता.",
                data={"manager_phone": store_phone},
                suggested_actions=["WhatsApp वरून किराणा ऑर्डर", "दुकान वेळ व पत्ता", "ऑर्डर ट्रॅक करा"],
            )

        # ---------------------------------------------------------
        # PRIORITY 11: INTENT: STORE FAQ & TIMINGS / ADDRESS
        # ---------------------------------------------------------
        faq_keywords = [
            "पत्ता", "address", "वेळ", "timing", "hours", "कधी चालू", "उघडे", "open",
            "phone", "फोन", "नंबर", "संपर्क", "contact", "location", "कुठे आहे दुकान", "patta", "vel", "kadhi ughadte"
        ]
        if any(k in q_lower for k in faq_keywords):
            faq = self.get_store_faq()
            lines = [
                f"• 📍 **पत्ता:** {faq['address']}",
                f"• ⏰ **दुकान वेळ:** {faq['operating_hours']}"
            ]
            if faq.get("phone") and faq["phone"] != "उपलब्ध नाही":
                lines.append(f"• 📞 **फोन / WhatsApp:** `{faq['phone']}`")
            if faq.get("email") and faq["email"] != "उपलब्ध नाही":
                lines.append(f"• ✉️ **ईमेल:** `{faq['email']}`")
            lines.append(f"• 💳 **पेमेंट पर्याय:** {faq['payment_methods']}")
            lines.append(f"• 🔄 **रिटर्न पॉलिसी:** {faq['return_policy']}")

            reply = (
                f"🏪 *{faq['store_name']} - माहिती व संपर्क*\n\n"
                + "\n".join(lines)
            )
            speech = f"{faq['store_name']} चा पत्ता {faq['address']} असा आहे."
            return CustomerSupportQueryResponse(
                intent="faq_store_info",
                reply=reply,
                speech_text=speech,
                data=faq,
                suggested_actions=["WhatsApp वरून किराणा ऑर्डर", "सर्व शाखांची माहिती", "ऑर्डर ट्रॅक करा"],
            )

        # ---------------------------------------------------------
        # PRIORITY 12: ATTEMPT GEMINI GENAI FOR COMPLEX QUESTIONS
        # ---------------------------------------------------------
        faq_data = self.get_store_faq()
        gemini_res = self._call_gemini_support(q_clean, faq_data, language)
        if gemini_res:
            return gemini_res

        # ---------------------------------------------------------
        # PRIORITY 13: GREETINGS & WARM HELPFUL DISPATCHER
        # ---------------------------------------------------------
        greeting_words = ["hi", "hello", "namaste", "namaskar", "नमस्कार", "नमस्ते", "हेल्प", "help"]
        if any(w in q_lower for w in greeting_words) or len(q_clean) < 4:
            reply = (
                f"🙏 *नमस्कार! मी {store_name} चा 24/7 AI ग्राहक सहाय्यक (Customer Care Bot) आहे.*\n\n"
                f"मी तुम्हाला खालील सर्व सेवांमध्ये मदत करू शकतो:\n"
                f"1. 🛒 **किराणा माल खरेदी:** (उदा. *'saman order karaycha ahe'*)\n"
                f"2. 📦 **ऑर्डर ट्रॅकिंग:** (उदा. *'माझी ऑर्डर ORD-1001 कुठे आहे?'*)\n"
                f"3. 🧾 **जीएसटी बिल डाऊनलोड:** (उदा. *'माझे बिल हवे आहे'*)\n"
                f"4. 🏪 **दुकान वेळ व पत्ता:** (उदा. *'दुकान कधी उघडे असते?'*)\n"
                f"5. 🛵 **घरपोच डिलिव्हरी:** (उदा. *'डिलिव्हरी कशी मिळते?'*)\n\n"
                f"खाली आपला प्रश्न टाईप करा किंवा वरील पर्यायांवर क्लिक करा! ✨"
            )
            speech = f"नमस्कार! मी {store_name} चा सहाय्यक आहे. मी ऑर्डर करणे, ट्रॅक करणे किंवा बिल देणे यात मदत करू शकतो."
            actions = ["saman order karaycha ahe", "WhatsApp वरून किराणा ऑर्डर", "ऑर्डर ट्रॅक करा", "दुकान वेळ व पत्ता"]
            return CustomerSupportQueryResponse(
                intent="greeting",
                reply=reply,
                speech_text=speech,
                suggested_actions=actions,
            )

        # Fallback response (Guaranteed valid contact, helpful directions)
        fallback_contact = f"दुकानाच्या सपोर्ट टीमशी `{store_phone}` या नंबरवर थेट संपर्क साधा." if store_phone else f"{store_name} च्या व्यवस्थापनाशी दुकानात थेट संपर्क साधा."
        reply = (
            f"🙏 *{store_name} ग्राहक सेवा मदत केंद्र*\n\n"
            f"आपल्या प्रश्नाबाबत अचूक माहिती मिळवण्यासाठी कृपया खालीलपैकी एक पर्याय निवडा:\n\n"
            f"• 🛒 **माल मागवण्यासाठी:** टाइप करा *'saman order karaycha ahe'*\n"
            f"• 📦 **ऑर्डर ट्रॅक करण्यासाठी:** आपला ऑर्डर नंबर टाइप करा (उदा. *ORD-1001*)\n"
            f"• 📞 **थेट मदतीसाठी:** {fallback_contact}"
        )
        speech = f"आपल्या मदतीसाठी आपण {store_phone} वर संपर्क करू शकता किंवा खालील पर्याय निवडू शकता." if store_phone else "आपल्या मदतीसाठी खालील पर्याय निवडू शकता."
        return CustomerSupportQueryResponse(
            intent="general",
            reply=reply,
            speech_text=speech,
            suggested_actions=["saman order karaycha ahe", "WhatsApp वरून किराणा ऑर्डर", "ऑर्डर ट्रॅक करा", "दुकान वेळ व पत्ता"],
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
