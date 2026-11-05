import base64
import json
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppException, NotFoundException
from app.core.logger import logger
from app.models.product import Product
from app.models.store import Store
from app.services.cart_service import CartService

settings = get_settings()

MARATHI_DIGITS_MAP = {
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}

UNIT_SYNONYMS = {
    "kg": ["kg", "kilo", "किलो", "किग्रा"],
    "g": ["g", "gm", "gram", "ग्रॅम", "ग्राम"],
    "l": ["l", "ltr", "liter", "litre", "लिटर", "लीटर"],
    "ml": ["ml", "मिली"],
    "pcs": ["pcs", "piece", "packet", "pkt", "pack", "नग", "पाकीट", "बॉटल", "डबा", "बाटली", "box", "ब्रेड"],
}

VOICE_PRODUCT_SYNONYMS = {
    "बासमती तांदूळ": ["बासमती", "तांदूळ", "basmati", "rice", "tandul", "chawal", "चावल"],
    "फॉर्च्युन तेल": ["फॉर्च्युन", "फॉर्च्यून", "fortune", "तेल", "oil", "sunflower", "soyabean"],
    "साखर": ["साखर", "sugar", "shakkar", "madhur", "माधुर"],
    "दूध": ["दूध", "milk", "amul", "अमूल", "dudh", "taaza"],
    "ब्रेड": ["ब्रेड", "bread", "wibs", "pav", "पाव"],
    "गहू": ["गहू", "wheat", "gehu", "आटा", "atta", "aashirvaad"],
    "चहा": ["चहा", "tea", "chai", "red label", "taj mahal"],
    "साबण": ["साबण", "soap", "dettol", "lifebuoy", "lux"],
    "डाळ": ["डाळ", "dal", "toor dal", "तूर डाळ", "moong"],
    "बिस्कीट": ["बिस्कीट", "biscuit", "parle", "good day", "marie"],
}


def normalize_voice_digits(text: str) -> str:
    """Converts Marathi/Devanagari numerals to ASCII digits."""
    for dev, asc in MARATHI_DIGITS_MAP.items():
        text = text.replace(dev, asc)
    return text


class VoicePOSService:
    def __init__(self, db: Session):
        self.db = db

    # --------------------------------------------------------------------------
    # 1. Speech-to-Text: Audio File Transcription via Gemini
    # --------------------------------------------------------------------------

    def transcribe_audio_bytes(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
        """Converts cashier spoken audio blob to text transcript using Gemini 1.5 Flash Multimodal."""
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            logger.warning("GEMINI_API_KEY is not configured for voice audio transcription")
            return ""

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        clean_mime = mime_type.split(";")[0].strip() or "audio/webm"

        system_instruction = (
            "You are a fast, high-accuracy Indian Retail POS Speech-to-Text engine. "
            "Transcribe the cashier's voice command spoken in Marathi, Hindi, English, or mixed. "
            "Accurately capture quantities, product names, brand names, and payment cash amounts. "
            "Return ONLY the exact transcribed text string without any commentary or quotation marks."
        )

        url = f"{settings.GEMINI_API_URL}/models/{settings.GEMINI_MODEL}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": clean_mime,
                                "data": audio_b64,
                            }
                        },
                        {
                            "text": "Transcribe this retail cashier billing voice command:"
                        }
                    ]
                }
            ],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {"temperature": 0.1},
        }

        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
        except Exception as exc:
            logger.error("Error transcribing voice audio with Gemini: %s", exc)

        return ""

    # --------------------------------------------------------------------------
    # 2. Voice Command Extraction: Tender, Items, Quantities
    # --------------------------------------------------------------------------

    def extract_tender_info(self, command: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """Extracts cashier tender/payment statement like 'रोख ५००' or 'cash 500'."""
        text = normalize_voice_digits(command)
        tender_info = None

        # Pattern 1: रोख <amount> / cash <amount> (e.g. 'रोख ५००', 'cash 500', 'नगद 1000')
        p1 = re.search(r"\b(रोख|cash|नगद|रोकड|पेमेंट|रोखड)\s*(?:रुपये|rs|inr)?\s*(\d+(?:\.\d+)?)\b", text, flags=re.IGNORECASE)
        # Pattern 2: <amount> रोख / <amount> cash (e.g. '५०० रोख', '500 cash')
        p2 = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:रुपये|rs|inr)?\s*(रोख|cash|नगद|रोकड)\b", text, flags=re.IGNORECASE)
        # Pattern 3: online / upi / card <amount>
        p3 = re.search(r"\b(online|upi|कार्ड|card|gpay|phonepe)\s*(?:रुपये|rs|inr)?\s*(\d+(?:\.\d+)?)?\b", text, flags=re.IGNORECASE)

        if p1:
            mode_raw, amt_str = p1.groups()
            tender_info = {"payment_mode": "cash", "tendered_amount": Decimal(amt_str)}
            text = text[:p1.start()] + " " + text[p1.end():]
        elif p2:
            amt_str, mode_raw = p2.groups()
            tender_info = {"payment_mode": "cash", "tendered_amount": Decimal(amt_str)}
            text = text[:p2.start()] + " " + text[p2.end():]
        elif p3:
            mode_raw, amt_str = p3.groups()
            mode = "upi" if mode_raw.lower() in ("online", "upi", "gpay", "phonepe") else "card"
            tender_info = {
                "payment_mode": mode,
                "tendered_amount": Decimal(amt_str) if amt_str else Decimal("0.00"),
            }
            text = text[:p3.start()] + " " + text[p3.end():]

        # Clean punctuation left over
        text = re.sub(r"[\.,;]+$", "", text).strip()
        return tender_info, text

    def extract_voice_items(self, text: str) -> List[Dict[str, Any]]:
        """Extracts items, units, and quantities from the items portion of the voice command."""
        text = normalize_voice_digits(text)
        items: List[Dict[str, Any]] = []

        delimiters = r"[,;\n+]|\s+आणि\s+|\s+and\s+|\s+aur\s+|\s+व\s+"
        segments = [s.strip() for s in re.split(delimiters, text, flags=re.IGNORECASE) if s.strip()]

        for seg in segments:
            clean_seg = re.sub(
                r"\b(द्या|द्यायचं|पाठवा|घ्या|कार्ट|मध्ये|ॲड|करा|टाका|add|cart|item|please|pls)\b",
                "",
                seg,
                flags=re.IGNORECASE,
            ).strip()

            if not clean_seg:
                continue

            # Pattern A: <qty> <optional_unit> <item_name> OR <qty> <item_name>
            match_a = re.search(r"(\d+(?:\.\d+)?)\s*([^\d\s]+)?\s*(.*)", clean_seg)
            # Pattern B: <item_name> <qty> <optional_unit>
            match_b = re.search(r"(.+?)\s+(\d+(?:\.\d+)?)\s*([^\d\s]+)?$", clean_seg)

            if match_a:
                qty_str, word1, rest = match_a.groups()
                qty = float(qty_str)
                word1 = (word1 or "").strip()
                rest = (rest or "").strip()

                matched_unit = "pcs"
                unit_found = False
                for std_unit, syns in UNIT_SYNONYMS.items():
                    if word1.lower() in syns:
                        matched_unit = std_unit
                        unit_found = True
                        break

                if unit_found:
                    item_name = rest
                else:
                    item_name = f"{word1} {rest}".strip()

                item_name = re.sub(
                    r"\b(द्या|घ्या|कार्ट|मध्ये|ॲड|करा|टाका|add|cart|item|please|pls)\b",
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
                for std_unit, syns in UNIT_SYNONYMS.items():
                    if unit.lower() in syns:
                        matched_unit = std_unit
                        break

                name = re.sub(
                    r"\b(द्या|घ्या|कार्ट|मध्ये|ॲड|करा|टाका|add|cart|item|please|pls)\b",
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

    # --------------------------------------------------------------------------
    # 3. Catalog Matching
    # --------------------------------------------------------------------------

    def match_product(self, tenant_id: int, query_name: str) -> Optional[Product]:
        """Fuzzy/Synonym catalog search for retail product."""
        clean_q = query_name.lower().strip()

        # 1. Exact or substring match in name or SKU or barcode
        product = (
            self.db.query(Product)
            .filter(
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
                (Product.name.ilike(f"%{clean_q}%") | (Product.sku == clean_q)),
            )
            .first()
        )
        if product:
            return product

        # 2. Check brand + product combo (e.g. 'फॉर्च्युन तेल' -> Brand Fortune or Name Fortune Oil)
        for std_key, synonyms in VOICE_PRODUCT_SYNONYMS.items():
            if any(syn in clean_q for syn in synonyms):
                for syn in synonyms:
                    p = (
                        self.db.query(Product)
                        .filter(
                            Product.tenant_id == tenant_id,
                            Product.is_active.is_(True),
                            (Product.name.ilike(f"%{syn}%") | Product.brand.ilike(f"%{syn}%")),
                        )
                        .first()
                    )
                    if p:
                        return p

        # 3. Individual words in query
        words = clean_q.split()
        for w in words:
            if len(w) >= 3:
                p = (
                    self.db.query(Product)
                    .filter(
                        Product.tenant_id == tenant_id,
                        Product.is_active.is_(True),
                        (Product.name.ilike(f"%{w}%") | Product.brand.ilike(f"%{w}%")),
                    )
                    .first()
                )
                if p:
                    return p

        return None

    # --------------------------------------------------------------------------
    # 4. Main Pipeline: Process Voice Command & Update Cart
    # --------------------------------------------------------------------------

    def process_voice_billing(
        self,
        tenant_id: int,
        user_id: int,
        command: str,
        store_id: Optional[int] = None,
        same_state: bool = True,
        language: str = "mr",
    ) -> dict:
        """
        Executes a voice billing command:
        1. Extracts tender/payment cash intent.
        2. Extracts items and quantities.
        3. Matches items with catalog and adds them to cashier's active billing cart.
        4. Calculates change due.
        5. Returns structured response with natural voice feedback.
        """
        raw_command = command.strip()
        tender_info, items_command = self.extract_tender_info(raw_command)
        parsed_items = self.extract_voice_items(items_command)

        cart_svc = CartService(self.db)
        items_added: List[Dict[str, Any]] = []
        unmatched_items: List[str] = []

        # Resolve effective store_id
        effective_store_id = store_id
        if not effective_store_id:
            store = (
                self.db.query(Store)
                .filter(Store.tenant_id == tenant_id, Store.is_active.is_(True))
                .order_by(Store.is_main.desc(), Store.id.asc())
                .first()
            )
            if store:
                effective_store_id = store.id

        if not effective_store_id:
            raise NotFoundException("No active store found for billing")

        for item in parsed_items:
            raw_name = item["item_name"]
            qty = Decimal(str(item["quantity"]))
            product = self.match_product(tenant_id, raw_name)

            if product:
                cart_svc.add_item(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    store_id=effective_store_id,
                    product_id=product.id,
                    quantity=qty,
                    same_state=same_state,
                )
                unit_price = Decimal(str(product.selling_price))
                tax_rate = Decimal(str(product.tax_rate or Decimal("0.00")))
                item_tot = (unit_price * qty).quantize(Decimal("0.01"))
                tax_amt = ((item_tot * tax_rate) / Decimal("100.00")).quantize(Decimal("0.01"))

                items_added.append({
                    "product_id": product.id,
                    "product_name": product.name,
                    "sku": product.sku or "",
                    "quantity": qty,
                    "unit": product.unit or item["unit"],
                    "unit_price": unit_price,
                    "tax_amount": tax_amt,
                    "total_amount": item_tot,
                })
            else:
                unmatched_items.append(raw_name)

        # Retrieve updated cart summary
        updated_cart = cart_svc.get_cart(tenant_id, user_id)
        grand_total = Decimal(str(updated_cart.get("grand_total", "0.00")))

        # Tender Calculation
        tender_resp = None
        if tender_info:
            tendered_amt = tender_info["tendered_amount"]
            change_due = max(Decimal("0.00"), (tendered_amt - grand_total).quantize(Decimal("0.01")))
            tender_resp = {
                "payment_mode": tender_info["payment_mode"],
                "tendered_amount": tendered_amt,
                "grand_total": grand_total,
                "change_due": change_due,
            }

        # Build natural voice feedback text
        voice_feedback = self._build_voice_feedback(
            items_added=items_added,
            unmatched_items=unmatched_items,
            grand_total=grand_total,
            tender=tender_resp,
            language=language,
        )

        return {
            "recognized_command": raw_command,
            "items_added": items_added,
            "unmatched_items": unmatched_items,
            "tender": tender_resp,
            "cart": updated_cart,
            "voice_feedback": voice_feedback,
        }

    # --------------------------------------------------------------------------
    # 5. Natural Voice Feedback Builder
    # --------------------------------------------------------------------------

    def _build_voice_feedback(
        self,
        items_added: List[Dict[str, Any]],
        unmatched_items: List[str],
        grand_total: Decimal,
        tender: Optional[Dict[str, Any]],
        language: str = "mr",
    ) -> str:
        """Constructs concise voice/spoken feedback for cashier audio response."""
        is_mr = language in ("mr", "marathi")

        if is_mr:
            parts = []
            if items_added:
                item_names = ", ".join([f"{it['product_name']}" for it in items_added[:2]])
                parts.append(f"{len(items_added)} वस्तू कार्टमध्ये जोडल्या ({item_names}). एकूण रक्कम ₹{grand_total:,.2f}.")
            elif unmatched_items:
                parts.append("कोणतीही वस्तू कार्टमध्ये जोडली गेली नाही.")

            if unmatched_items:
                parts.append(f" ('{', '.join(unmatched_items)}' कॅटलॉगमध्ये सापडले नाही).")

            if tender:
                t_amt = tender["tendered_amount"]
                c_due = tender["change_due"]
                if c_due > 0:
                    parts.append(f" रोख ₹{t_amt:,.2f} पैकी ₹{c_due:,.2f} परत द्या.")
                elif t_amt < grand_total:
                    parts.append(f" रोख ₹{t_amt:,.2f} मिळाली, ₹{(grand_total - t_amt):,.2f} बाकी आहेत.")
                else:
                    parts.append(f" रोख ₹{t_amt:,.2f} पूर्ण मिळाले.")

            return "".join(parts).strip() or "आदेश समजला नाही."
        else:
            # English
            parts = []
            if items_added:
                parts.append(f"Added {len(items_added)} items to cart. Grand total ₹{grand_total:,.2f}.")
            if unmatched_items:
                parts.append(f" Could not find: {', '.join(unmatched_items)}.")
            if tender:
                t_amt = tender["tendered_amount"]
                c_due = tender["change_due"]
                if c_due > 0:
                    parts.append(f" Cash ₹{t_amt:,.2f} tendered. Return ₹{c_due:,.2f} change.")
                else:
                    parts.append(f" Paid ₹{t_amt:,.2f}.")

            return "".join(parts).strip() or "Command not recognized."

