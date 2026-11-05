import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logger import logger
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.store import Store
from app.models.whatsapp import WhatsAppSetting, WhatsAppLog
from app.services.whatsapp_service import WhatsAppService, normalize_whatsapp_phone
from app.utils.constants import OrderStatus

settings = get_settings()

MARATHI_DIGITS_MAP = {
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}

UNIT_SYNONYMS = {
    "kg": ["kg", "kilo", "किलो", "किग्रा"],
    "g": ["g", "gm", "gram", "ग्रॅम", "ग्राम"],
    "l": ["l", "ltr", "liter", "litre", "लिटर"],
    "ml": ["ml", "मिली"],
    "pcs": ["pcs", "piece", "packet", "pkt", "pack", "नग", "पाकीट", "बॉटल", "डबा", "बाटली", "box"],
}

PRODUCT_SYNONYMS = {
    "साखर": ["साखर", "sugar", "shakkar", "madhur"],
    "दूध": ["दूध", "milk", "dudh", "amul milk", "अमूल दूध", "taaza"],
    "ब्रेड": ["ब्रेड", "bread", "pav", "पाव", "wibs"],
    "तांदूळ": ["तांदूळ", "rice", "tandul", "chawal", "चावल", "basmati"],
    "गहू": ["गहू", "wheat", "gehu", "गेहू", "atta", "आटा"],
    "तेल": ["तेल", "oil", "tel", "cooking oil", "fortune"],
    "चहा": ["चहा", "tea", "chai", "चाय", "tea powder", "red label"],
    "कांदा": ["कांदा", "onion", "kanda", "pyaz", "प्याज़"],
    "बटाटा": ["बटाटा", "potato", "batata", "aloo", "आलू"],
    "साबण": ["साबण", "soap", "saban", "handwash", "dettol"],
}


def normalize_digits(text: str) -> str:
    """Converts Marathi/Devanagari numerals to ASCII digits."""
    for dev, asc in MARATHI_DIGITS_MAP.items():
        text = text.replace(dev, asc)
    return text


class WhatsAppOrderingService:
    def __init__(self, db: Session):
        self.db = db

    def resolve_setting_and_store(
        self, phone_number_id: Optional[str] = None
    ) -> Tuple[Optional[WhatsAppSetting], Optional[Store]]:
        """Finds WhatsAppSetting and corresponding Store."""
        setting = None
        if phone_number_id:
            setting = (
                self.db.query(WhatsAppSetting)
                .filter(WhatsAppSetting.phone_number_id == phone_number_id)
                .first()
            )
        if not setting:
            setting = (
                self.db.query(WhatsAppSetting)
                .filter(WhatsAppSetting.is_enabled.is_(True))
                .first()
            )
        if not setting:
            return None, None

        store = None
        if setting.store_id:
            store = self.db.query(Store).filter(Store.id == setting.store_id).first()
        if not store:
            store = (
                self.db.query(Store)
                .filter(Store.tenant_id == setting.tenant_id, Store.is_active.is_(True))
                .order_by(Store.is_main.desc(), Store.id.asc())
                .first()
            )
        return setting, store

    def get_or_create_customer(
        self, tenant_id: int, phone: str, sender_name: Optional[str] = None
    ) -> Customer:
        """Finds or registers a customer by WhatsApp phone number."""
        clean_phone = normalize_whatsapp_phone(phone)
        short_phone = clean_phone[-10:] if len(clean_phone) >= 10 else clean_phone

        customer = (
            self.db.query(Customer)
            .filter(
                Customer.tenant_id == tenant_id,
                (Customer.phone == clean_phone) | (Customer.phone == short_phone),
            )
            .first()
        )
        if not customer:
            display_name = sender_name or f"WhatsApp Customer {short_phone[-4:]}"
            customer = Customer(
                tenant_id=tenant_id,
                name=display_name,
                phone=short_phone,
                whatsapp_opt_in=True,
                status="active",
                segment="whatsapp",
            )
            self.db.add(customer)
            self.db.commit()
            self.db.refresh(customer)
        return customer

    # --------------------------------------------------------------------------
    # Intent Detection & Item Parsing
    # --------------------------------------------------------------------------

    def parse_items_with_gemini(self, message_body: str) -> Optional[List[Dict[str, Any]]]:
        """Uses Gemini GenAI to parse natural language order items if configured."""
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            return None

        prompt = (
            f"You are a retail POS parsing engine. A customer sent this grocery/retail order message "
            f"in Marathi, Hindi, or English:\n\n"
            f'"{message_body}"\n\n'
            f"Extract the items, their desired quantity (number), and unit (kg, ltr, pcs, pack, etc.).\n"
            f'Return ONLY a valid JSON list of objects: [{{"item_name": "...", "quantity": 1, "unit": "..."}}].\n'
            f"If no specific grocery/store item is requested, return []."
        )
        url = f"{settings.GEMINI_API_URL}/models/{settings.GEMINI_MODEL}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        try:
            import httpx
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    parsed = json.loads(raw_text)
                    if isinstance(parsed, list) and len(parsed) > 0:
                        return parsed
        except Exception as exc:
            logger.warning("Gemini order parsing failed: %s", exc)
        return None

    def parse_items_rule_based(self, message_body: str) -> List[Dict[str, Any]]:
        """Deterministic regex and keyword parsing for Marathi, Hindi, and English orders."""
        text = normalize_digits(message_body)
        items: List[Dict[str, Any]] = []

        # Split message into item phrases by commas, semicolons, newlines, '+', 'आणि', 'and', 'aur', 'व'
        delimiters = r"[,;\n+]|\s+आणि\s+|\s+and\s+|\s+aur\s+|\s+व\s+"
        phrases = [p.strip() for p in re.split(delimiters, text, flags=re.IGNORECASE) if p.strip()]

        for phrase in phrases:
            cleaned_phrase = re.sub(
                r"\b(मला|घरी|पाठवा|हवे|हवी|आहे|द्या|पाहिजे|home|send|deliver|please|order|pls|हव)\b",
                "",
                phrase,
                flags=re.IGNORECASE,
            ).strip()

            if not cleaned_phrase:
                continue

            # Pattern A: <qty> <optional_unit> <item_name> OR <qty> <item_name>
            match_a = re.search(r"(\d+(?:\.\d+)?)\s*([^\d\s]+)?\s*(.*)", cleaned_phrase)
            # Pattern B: <item_name> <qty> <optional_unit>
            match_b = re.search(r"(.+?)\s+(\d+(?:\.\d+)?)\s*([^\d\s]+)?$", cleaned_phrase)

            if match_a:
                qty_str, word1, rest = match_a.groups()
                qty = float(qty_str)
                word1 = (word1 or "").strip()
                rest = (rest or "").strip()

                matched_unit = "pcs"
                unit_found = False
                for std_unit, synonyms in UNIT_SYNONYMS.items():
                    if word1.lower() in synonyms:
                        matched_unit = std_unit
                        unit_found = True
                        break

                if unit_found:
                    item_name = rest
                else:
                    item_name = f"{word1} {rest}".strip()

                item_name = re.sub(
                    r"\b(मला|घरी|पाठवा|हवे|हवी|आहे|द्या|पाहिजे|home|send|deliver|please|order|pls|हव)\b",
                    "",
                    item_name,
                    flags=re.IGNORECASE,
                ).strip()

                if item_name:
                    items.append({
                        "item_name": item_name,
                        "quantity": max(1, int(round(qty))),
                        "unit": matched_unit,
                    })

            elif match_b:
                name_cand, qty_str, unit_cand = match_b.groups()
                qty = float(qty_str)
                name = name_cand.strip()
                unit = (unit_cand or "pcs").strip()
                matched_unit = "pcs"
                for std_unit, synonyms in UNIT_SYNONYMS.items():
                    if unit.lower() in synonyms:
                        matched_unit = std_unit
                        break

                name = re.sub(
                    r"\b(मला|घरी|पाठवा|हवे|हवी|आहे|द्या|पाहिजे|home|send|deliver|please|order|pls|हव)\b",
                    "",
                    name,
                    flags=re.IGNORECASE,
                ).strip()

                if name:
                    items.append({
                        "item_name": name,
                        "quantity": max(1, int(round(qty))),
                        "unit": matched_unit,
                    })

        return items

    def match_product_in_catalog(
        self, tenant_id: int, query_name: str
    ) -> Optional[Product]:
        """Fuzzy/Synonym search in store's active product catalog."""
        clean_q = query_name.lower().strip()
        # Direct exact or substring match
        product = (
            self.db.query(Product)
            .filter(
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
                Product.name.ilike(f"%{clean_q}%"),
            )
            .first()
        )
        if product:
            return product

        # Check dictionary of common Marathi/English synonyms
        for standard_key, synonyms in PRODUCT_SYNONYMS.items():
            if any(syn in clean_q for syn in synonyms):
                for syn in synonyms:
                    product = (
                        self.db.query(Product)
                        .filter(
                            Product.tenant_id == tenant_id,
                            Product.is_active.is_(True),
                            Product.name.ilike(f"%{syn}%"),
                        )
                        .first()
                    )
                    if product:
                        return product

        # Try individual words in query
        words = clean_q.split()
        for w in words:
            if len(w) >= 3:
                product = (
                    self.db.query(Product)
                    .filter(
                        Product.tenant_id == tenant_id,
                        Product.is_active.is_(True),
                        Product.name.ilike(f"%{w}%"),
                    )
                    .first()
                )
                if product:
                    return product

        return None

    # -------------------------------------------------------------
    # Main Processing Pipeline
    # -------------------------------------------------------------

    def process_inbound_message(
        self,
        from_phone: str,
        message_body: str,
        sender_name: Optional[str] = None,
        phone_number_id: Optional[str] = None,
    ) -> dict:
        """Processes an incoming customer WhatsApp message and replies appropriately."""
        setting, store = self.resolve_setting_and_store(phone_number_id)
        if not setting or not setting.is_enabled:
            return {"status": "skipped", "reason": "WhatsApp integration disabled"}

        if not setting.ai_ordering_enabled:
            return {"status": "skipped", "reason": "AI Conversational Ordering is turned off"}

        tenant_id = setting.tenant_id
        store_id = store.id if store else None
        store_name = store.name if store else "Retail-OS Store"

        # Customer record
        customer = self.get_or_create_customer(tenant_id, from_phone, sender_name)
        customer_name = customer.name or "ग्राहक"

        text_clean = message_body.strip().lower()
        normalized_digits_text = normalize_digits(text_clean)
        has_digits = any(ch.isdigit() for ch in normalized_digits_text)

        # 1. GREETING / CATALOG REQUEST (When no item quantity digits are present)
        greeting_words = [
            "hi", "hello", "hey", "namaste", "namaskar", "नमस्कार", "नमस्ते",
            "menu", "list", "products", "item", "काही आहे", "भाव", "ऑर्डर करायची",
        ]
        if any(w in text_clean for w in greeting_words) and not has_digits:
            reply_text = self._build_welcome_reply(store_name, customer_name, setting)
            self._send_and_log(setting, from_phone, reply_text, "greeting")
            return {"status": "success", "intent": "greeting", "reply": reply_text}

        # 2. STATUS INQUIRY
        status_words = ["status", "order status", "कुठे आहे", "माझी ऑर्डर", "delivery", "kiti vel"]
        if any(w in text_clean for w in status_words):
            latest_order = (
                self.db.query(Order)
                .filter(Order.tenant_id == tenant_id, Order.customer_id == customer.id)
                .order_by(Order.id.desc())
                .first()
            )
            if latest_order:
                reply_text = (
                    f"📦 *ऑर्डर स्थिती (Order Status)*\n"
                    f"नमस्ते {customer_name}! आपली ऑर्डर #{latest_order.order_number} सध्या *{latest_order.status.upper()}* स्थितीत आहे.\n"
                    f"एकूण रक्कम: ₹{float(latest_order.total_amount):,.2f}.\n"
                    f"काही अडचण असल्यास कृपया दुकानाशी संपर्क साधा."
                )
            else:
                reply_text = f"नमस्ते {customer_name}! आपल्या नावावर सध्या कोणतीही चालू ऑर्डर आढळली नाही. नवीन ऑर्डर करण्यासाठी वस्तूंची यादी मेसेज करा."

            self._send_and_log(setting, from_phone, reply_text, "status")
            return {"status": "success", "intent": "status", "reply": reply_text}

        # 3. CONVERSATIONAL ORDER CREATION
        parsed_items = self.parse_items_with_gemini(message_body) or self.parse_items_rule_based(message_body)

        if not parsed_items:
            # Fallback help message
            reply_text = (
                f"नमस्ते {customer_name}!\n"
                f"आम्हाला आपल्या मेसेजमधून नेमकी कोणती उत्पादने हवी आहेत ते समजले नाही. 🤔\n\n"
                f"कृपया वस्तूचे नाव आणि प्रमाण स्पष्ट लिहा. उदा:\n"
                f"👉 *'१ किलो साखर, २ लिटर अमूल दूध आणि १ ब्रेड घरी पाठवा'*.\n"
                f"धन्यवाद! 🙏"
            )
            self._send_and_log(setting, from_phone, reply_text, "help_prompt")
            return {"status": "success", "intent": "unknown", "reply": reply_text}

        # Match items with store products
        matched_items: List[Dict[str, Any]] = []
        unmatched_names: List[str] = []
        subtotal = Decimal("0.00")
        total_tax = Decimal("0.00")

        for item in parsed_items:
            raw_name = item.get("item_name", "")
            qty = Decimal(str(item.get("quantity", 1)))
            product = self.match_product_in_catalog(tenant_id, raw_name)

            if product:
                price = product.selling_price
                tax_rate = getattr(product, "tax_rate", Decimal("0.00")) or Decimal("0.00")
                item_total = price * qty
                item_tax = (item_total * tax_rate) / Decimal("100.00")

                subtotal += item_total
                total_tax += item_tax

                matched_items.append({
                    "product": product,
                    "quantity": int(qty),
                    "price": price,
                    "tax": item_tax,
                    "total": item_total,
                    "unit": product.unit or item.get("unit", "pcs"),
                })
            else:
                unmatched_names.append(raw_name)

        if not matched_items:
            unmatched_str = ", ".join(unmatched_names)
            reply_text = (
                f"दिलगीर आहोत {customer_name}! आपण मागवलेली उत्पादने ({unmatched_str}) "
                f"सध्या {store_name} मध्ये उपलब्ध नाहीत. कृपया इतर वस्तू तपासा."
            )
            self._send_and_log(setting, from_phone, reply_text, "out_of_stock")
            return {"status": "success", "intent": "out_of_stock", "reply": reply_text}

        # Create Order in Retail-OS database
        order_total = subtotal + total_tax
        order_number = f"ORD-WA-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        new_order = Order(
            tenant_id=tenant_id,
            store_id=store_id,
            customer_id=customer.id,
            order_number=order_number,
            order_type="ecommerce",
            status=OrderStatus.CONFIRMED.value,
            subtotal=subtotal,
            tax_amount=total_tax,
            total_amount=order_total,
            notes=f"Auto-generated via WhatsApp Conversational AI. Original: {message_body[:100]}",
        )
        self.db.add(new_order)
        self.db.flush()

        for m in matched_items:
            prod = m["product"]
            order_item = OrderItem(
                order_id=new_order.id,
                product_id=prod.id,
                product_name=prod.name,
                sku=prod.sku,
                quantity=m["quantity"],
                unit_price=m["price"],
                tax_amount=m["tax"],
                total=m["total"],
                total_amount=m["total"],
            )
            self.db.add(order_item)

        self.db.commit()
        self.db.refresh(new_order)

        # Generate UPI Link
        vpa = setting.upi_vpa or getattr(store, "phone", None) or settings.SAAS_UPI_VPA or "retailos@icici"
        if vpa and "@" not in vpa:
            vpa = f"{vpa}@upi"
        payee_name = setting.upi_payee_name or store_name
        upi_link = (
            f"upi://pay?pa={vpa}&pn={payee_name}&am={float(order_total):.2f}&cu=INR&tn=Order_{order_number}"
        )

        # Compose WhatsApp Order Confirmation Message
        item_lines = []
        for idx, m in enumerate(matched_items, 1):
            pname = m["product"].name
            iqty = m["quantity"]
            iunit = m["unit"]
            itot = float(m["total"])
            item_lines.append(f"{idx}. *{pname}* ({iqty} {iunit}) — ₹{itot:,.2f}")

        items_str = "\n".join(item_lines)
        unmatched_note = ""
        if unmatched_names:
            unmatched_note = f"\n\n⚠️ *टीप:* '{', '.join(unmatched_names)}' सध्या उपलब्ध नाही."

        reply_text = (
            f"🛒 *{store_name} - ऑर्डर तयार झाली!*\n"
            f"नमस्ते {customer_name}! आपली ऑर्डर नोंदवली गेली आहे:\n\n"
            f"{items_str}\n"
            f"--------------------------------\n"
            f"💰 *एकूण देय रक्कम: ₹{float(order_total):,.2f}*\n"
            f"📑 ऑर्डर क्रमांक: *#{order_number}*"
            f"{unmatched_note}\n\n"
            f"💳 *पेमेंट करण्यासाठी खालील UPI लिंकवर क्लिक करा:*\n"
            f"{upi_link}\n\n"
            f"पेमेंट पूर्ण झाल्यावर आपली ऑर्डर लगेच पॅक करून पाठवली जाईल. धन्यवाद! 🙏"
        )

        self._send_and_log(
            setting=setting,
            to_phone=from_phone,
            message=reply_text,
            message_type="whatsapp_order_confirmation",
            order_id=new_order.id,
        )

        return {
            "status": "success",
            "intent": "order_created",
            "order_id": new_order.id,
            "order_number": order_number,
            "total_amount": float(order_total),
            "upi_link": upi_link,
            "reply": reply_text,
        }

    # -------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------

    def _build_welcome_reply(
        self, store_name: str, customer_name: str, setting: WhatsAppSetting
    ) -> str:
        if setting.ai_welcome_message:
            return setting.ai_welcome_message.format(customer_name=customer_name, store_name=store_name)

        return (
            f"🙏 *{store_name} मध्ये आपले स्वागत आहे!*\n"
            f"नमस्ते {customer_name}! मी आपला AI व्हॉट्सॲप शॉपिंग असिस्टंट आहे.\n\n"
            f"🛒 *घरबसल्या ऑर्डर कशी करावी?*\n"
            f"फक्त आपल्याला हव्या असलेल्या वस्तू आणि प्रमाण मेसेज करा. उदा:\n"
            f"👉 *'१ किलो साखर, २ लिटर अमूल दूध आणि १ ब्रेड घरी पाठवा'*\n\n"
            f"आम्ही लगेच ऑर्डर तयार करून पेमेंटसाठी थेट UPI लिंक पाठवू! ✨"
        )

    def _send_and_log(
        self,
        setting: WhatsAppSetting,
        to_phone: str,
        message: str,
        message_type: str,
        order_id: Optional[int] = None,
    ) -> dict:
        service = WhatsAppService(db=self.db, tenant_id=setting.tenant_id, store_id=setting.store_id)
        res = service.send_message(to_phone, message)
        return res
