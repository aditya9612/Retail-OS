from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import re
from typing import Any, Dict, List, Optional, Tuple
import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import NotFoundException, AppException
from app.core.logger import logger
from app.models.customer import Customer
from app.models.store import Store
from app.models.whatsapp import WhatsAppSetting, WhatsAppLog, KhataFollowup
from app.schemas.whatsapp import KhataPendingCustomerItem
from app.services.whatsapp_service import WhatsAppService, normalize_whatsapp_phone

settings = get_settings()


class SmartKhataService:
    def __init__(self, db: Session, tenant_id: int, store_id: Optional[int] = None):
        self.db = db
        self.tenant_id = tenant_id
        self.store_id = store_id

    def get_setting_and_store(self) -> Tuple[WhatsAppSetting, Optional[Store]]:
        """Loads WhatsAppSetting and Store context."""
        query = self.db.query(WhatsAppSetting).filter(WhatsAppSetting.tenant_id == self.tenant_id)
        if self.store_id:
            setting = query.filter(WhatsAppSetting.store_id == self.store_id).first()
        else:
            setting = query.filter(WhatsAppSetting.store_id.is_(None)).first()

        if not setting:
            setting = query.first()

        if not setting:
            setting = WhatsAppSetting(
                tenant_id=self.tenant_id,
                store_id=self.store_id,
                is_enabled=True,
                ai_khata_reminders_enabled=True,
                khata_min_balance=Decimal("100.00"),
            )
            self.db.add(setting)
            self.db.commit()
            self.db.refresh(setting)

        store = None
        if self.store_id:
            store = self.db.query(Store).filter(Store.id == self.store_id).first()
        if not store:
            store = (
                self.db.query(Store)
                .filter(Store.tenant_id == self.tenant_id, Store.is_active.is_(True))
                .order_by(Store.is_main.desc(), Store.id.asc())
                .first()
            )

        return setting, store

    # --------------------------------------------------------------------------
    # 1. LIST OVERDUE KHATA CUSTOMERS
    # --------------------------------------------------------------------------

    def get_pending_khata_customers(
        self, min_balance: Optional[float] = None
    ) -> List[KhataPendingCustomerItem]:
        """Lists customers who have an outstanding balance exceeding threshold."""
        setting, _ = self.get_setting_and_store()
        threshold = Decimal(str(min_balance)) if min_balance is not None else (setting.khata_min_balance or Decimal("100.00"))

        customers = (
            self.db.query(Customer)
            .filter(
                Customer.tenant_id == self.tenant_id,
                Customer.outstanding_balance >= threshold,
                Customer.status == "active",
            )
            .order_by(Customer.outstanding_balance.desc())
            .all()
        )

        results = []
        for cust in customers:
            latest_followup = (
                self.db.query(KhataFollowup)
                .filter(
                    KhataFollowup.tenant_id == self.tenant_id,
                    KhataFollowup.customer_id == cust.id,
                )
                .order_by(KhataFollowup.id.desc())
                .first()
            )

            rec_status = "pending"
            last_reminder_at = None
            last_promised_date = None

            if latest_followup:
                rec_status = latest_followup.status
                last_reminder_at = latest_followup.reminder_sent_at
                last_promised_date = latest_followup.promised_date

            results.append(
                KhataPendingCustomerItem(
                    customer_id=cust.id,
                    customer_name=cust.name or f"Customer #{cust.id}",
                    phone=cust.phone,
                    outstanding_balance=float(cust.outstanding_balance),
                    credit_limit=float(cust.credit_limit or Decimal("0.00")),
                    total_spend=float(cust.total_spend or 0),
                    last_reminder_at=last_reminder_at,
                    last_promised_date=last_promised_date,
                    recovery_status=rec_status,
                )
            )

        return results

    # --------------------------------------------------------------------------
    # 2. GENERATE & SEND PERSONALIZED REMINDER
    # --------------------------------------------------------------------------

    def build_reminder_message(
        self, customer: Customer, store_name: str, setting: WhatsAppSetting, custom_note: Optional[str] = None
    ) -> Tuple[str, str]:
        """Builds a respectful Marathi reminder message with exact UPI paylink."""
        amt = float(customer.outstanding_balance)
        cust_name = customer.name or "ग्राहक"

        # Generate UPI Pay Link
        vpa = setting.upi_vpa or settings.SAAS_UPI_VPA or "retailos@icici"
        if vpa and "@" not in vpa:
            vpa = f"{vpa}@upi"
        payee_name = setting.upi_payee_name or store_name

        upi_link = (
            f"upi://pay?pa={vpa}&pn={payee_name}&am={amt:.2f}&cu=INR&tn=Khata_Balance_{customer.id}"
        )

        note_str = f"\n📝 *टीप:* {custom_note}" if custom_note else ""

        message = (
            f"🙏 *{store_name} - खात्यावरील बाकी स्मरणपत्र (Khata Reminder)*\n\n"
            f"सस्नेह नमस्कार *{cust_name}* जी! आशा आहे आपण मजेत असाल.\n"
            f"आपल्या दुकानातील खात्यावर चालू थकबाकी रक्कम: *₹{amt:,.2f}* आहे.\n{note_str}\n"
            f"💳 *थेट GooglePay / PhonePe / Paytm द्वारे फेडण्यासाठी खालील UPI लिंकवर क्लिक करा:*\n"
            f"👉 {upi_link}\n\n"
            f"आपण आधीच पेमेंट केले असल्यास कृपया या मेसेजला उत्तर देऊन कळवावे. काही अडचण असल्यास बिनधास्त संपर्क करा.\n"
            f"आपल्या निरंतर सहकार्याबद्दल मनापासून धन्यवाद! 🙏✨"
        )

        return message, upi_link

    def send_khata_reminder(
        self, customer_id: int, custom_note: Optional[str] = None
    ) -> dict:
        """Sends a smart WhatsApp reminder to an overdue customer and logs a KhataFollowup."""
        customer = (
            self.db.query(Customer)
            .filter(Customer.id == customer_id, Customer.tenant_id == self.tenant_id)
            .first()
        )
        if not customer:
            raise NotFoundException("Customer not found")

        if customer.outstanding_balance <= Decimal("0.00"):
            return {
                "status": "skipped",
                "reason": "Customer has zero or negative outstanding balance",
                "customer_id": customer.id,
            }

        setting, store = self.get_setting_and_store()
        store_name = store.name if store else "Retail-OS Store"

        message, upi_link = self.build_reminder_message(customer, store_name, setting, custom_note)

        # Dispatch via WhatsAppService
        wa_service = WhatsAppService(db=self.db, tenant_id=self.tenant_id, store_id=self.store_id)
        res = wa_service.send_message(to=customer.phone, message=message)

        # Record in KhataFollowup
        followup = KhataFollowup(
            tenant_id=self.tenant_id,
            store_id=self.store_id,
            customer_id=customer.id,
            outstanding_amount=customer.outstanding_balance,
            reminder_sent_at=datetime.utcnow(),
            reminder_message=message,
            status="reminder_sent",
            meta_message_id=res.get("message_id"),
            notes=f"Reminder sent. UPI: {upi_link}",
        )
        self.db.add(followup)
        self.db.commit()
        self.db.refresh(followup)

        return {
            "status": "success",
            "customer_id": customer.id,
            "customer_name": customer.name,
            "outstanding_amount": float(customer.outstanding_balance),
            "followup_id": followup.id,
            "upi_link": upi_link,
            "whatsapp_result": res,
        }

    def broadcast_khata_reminders(
        self, min_balance: Optional[float] = None
    ) -> dict:
        """Broadcasts reminders to all qualifying customers."""
        candidates = self.get_pending_khata_customers(min_balance)
        sent_count = 0
        skipped_count = 0
        details = []

        for item in candidates:
            try:
                res = self.send_khata_reminder(item.customer_id)
                if res.get("status") == "success":
                    sent_count += 1
                else:
                    skipped_count += 1
                details.append(res)
            except Exception as exc:
                logger.error("Failed to send khata reminder to customer %s: %s", item.customer_id, exc)
                skipped_count += 1

        return {
            "status": "completed",
            "total_candidates": len(candidates),
            "sent_count": sent_count,
            "skipped_count": skipped_count,
            "details": details,
        }

    # --------------------------------------------------------------------------
    # 3. AI CUSTOMER REPLY PROCESSING & PROMISE-TO-PAY DETECTION
    # --------------------------------------------------------------------------

    def parse_reply_with_gemini(self, reply_text: str) -> Optional[dict]:
        """Calls Gemini LLM to extract customer intention and promise-to-pay date."""
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            return None

        prompt = (
            f"You are an AI Khata Credit Assistant for a retail merchant in India.\n"
            f"The customer replied to an outstanding credit balance reminder in Marathi, Hindi, or English:\n\n"
            f'"{reply_text}"\n\n'
            f"Classify the reply into an intent:\n"
            f"- 'promise_to_pay': customer agrees to pay on a specific day/date (e.g. 'उद्या देतो', 'after 2 days', 'Monday', '25 tarakhela')\n"
            f"- 'already_paid': customer claims they already paid or sent Google Pay/cash\n"
            f"- 'dispute': customer questions the balance or asks for invoice/bill check\n"
            f"- 'delay': customer is asking for more time or expressing financial hardship\n"
            f"- 'unknown': general or unrelated text\n\n"
            f"Also estimate the promised date (YYYY-MM-DD) based on today: {datetime.utcnow().strftime('%Y-%m-%d')}.\n"
            f'Output ONLY valid JSON: {{"intent": "...", "promised_date": "YYYY-MM-DD or null", "confidence": 0.9, "acknowledgment": "courteous reply in customer language"}}'
        )
        url = f"{settings.GEMINI_API_URL}/models/{settings.GEMINI_MODEL}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(url, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict) and "intent" in parsed:
                        return parsed
        except Exception as exc:
            logger.warning("Gemini Khata reply parsing failed: %s", exc)

        return None

    def parse_reply_rule_based(self, reply_text: str) -> dict:
        """Deterministic fallback intent & date detection for Marathi/English replies."""
        text = reply_text.lower().strip()
        today = datetime.utcnow().date()
        intent = "unknown"
        promised_date = None
        ack = ""

        # 1. ALREADY PAID
        if any(w in text for w in [
            "दिले", "दिलेले", "paid", "gpay", "google pay", "phonepe", "paytm",
            "गुगल पे", "फोन पे", "पेमेंट केले", "जमा केले", "पैसे पाठवले", "पाठवले आहेत", "पाठवले", "done"
        ]):
            intent = "already_paid"
            ack = "आपल्या उत्तरासाठी धन्यवाद! आम्ही आपले पेमेंट खात्यात तपासून लगेच अपडेट करत आहोत. 🙏"

        # 2. PROMISE TO PAY
        elif any(w in text for w in ["उद्या", "कल", "tomorrow"]):
            intent = "promise_to_pay"
            promised_date = today + timedelta(days=1)
            ack = f"धन्यवाद! आम्ही आपल्या नोंदीत उद्या ({promised_date.strftime('%d %b %Y')}) ची तारीख नोंदवली आहे. सहकार्याबद्दल आभार! 🙏"
        elif any(w in text for w in ["परवा", "parwa", "day after tomorrow"]):
            intent = "promise_to_pay"
            promised_date = today + timedelta(days=2)
            ack = f"धन्यवाद! आम्ही आपल्या नोंदीत परवा ({promised_date.strftime('%d %b %Y')}) ची तारीख नोंदवली आहे. 🙏"
        elif "सोमवारी" in text or "monday" in text:
            intent = "promise_to_pay"
            promised_date = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
            ack = f"धन्यवाद! आम्ही सोमवारी ({promised_date.strftime('%d %b %Y')}) ची नोंद ठेवली आहे. 🙏"
        elif "शनिवारी" in text or "saturday" in text:
            intent = "promise_to_pay"
            promised_date = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
            ack = f"धन्यवाद! शनिवारी ({promised_date.strftime('%d %b %Y')}) ची नोंद ठेवली आहे. 🙏"
        elif "रविवारी" in text or "sunday" in text:
            intent = "promise_to_pay"
            promised_date = today + timedelta(days=(6 - today.weekday()) % 7 or 7)
            ack = f"धन्यवाद! रविवारी ({promised_date.strftime('%d %b %Y')}) ची नोंद ठेवली आहे. 🙏"
        elif re.search(r"(\d+)\s*(दिवस|days|दिवसात)", text):
            m = re.search(r"(\d+)\s*(दिवस|days|दिवसात)", text)
            days_add = int(m.group(1)) if m else 3
            intent = "promise_to_pay"
            promised_date = today + timedelta(days=days_add)
            ack = f"धन्यवाद! आम्ही {days_add} दिवसांनंतरची ({promised_date.strftime('%d %b %Y')}) तारीख नोंदवून घेतली आहे. 🙏"

        # 3. DISPUTE
        elif any(w in text for w in ["तपासा", "चेक करा", "चूक", "wrong", "check", "बिल पाठवा", "माझे नाही"]):
            intent = "dispute"
            ack = "आपली विनंती नोंदवली आहे. आमचे स्टोअर मॅनेजर लवकरच आपले बिल तपासून आपल्याशी संपर्क साधतील. 🙏"

        # 4. DELAY / HARDSHIP
        elif any(w in text for w in ["सध्या नाही", "पगार झाल्यावर", "नंतर", "next month", "salary", "problem"]):
            intent = "delay"
            promised_date = today + timedelta(days=10)
            ack = "काही हरकत नाही! आम्ही आपल्या विनंतीनुसार पुढील तारीख नोंदवली आहे. सहकार्याबद्दल धन्यवाद. 🙏"

        else:
            intent = "unknown"
            ack = "आपल्या मेसेजसाठी धन्यवाद! काही अडचण असल्यास दुकानाशी संपर्क साधा. 🙏"

        return {
            "intent": intent,
            "promised_date": str(promised_date) if promised_date else None,
            "acknowledgment": ack,
        }

    def process_customer_khata_reply(
        self, customer_id: int, reply_text: str
    ) -> dict:
        """Processes an incoming customer reply to a Khata reminder and updates follow-up state."""
        customer = (
            self.db.query(Customer)
            .filter(Customer.id == customer_id, Customer.tenant_id == self.tenant_id)
            .first()
        )
        if not customer:
            raise NotFoundException("Customer not found")

        # Parse intent
        ai_result = self.parse_reply_with_gemini(reply_text) or self.parse_reply_rule_based(reply_text)
        intent = ai_result.get("intent", "unknown")
        promised_date_str = ai_result.get("promised_date")
        ack_message = ai_result.get("acknowledgment", "आपल्या मेसेजसाठी धन्यवाद! 🙏")

        parsed_date = None
        if promised_date_str:
            try:
                parsed_date = datetime.strptime(promised_date_str, "%Y-%m-%d").date()
            except Exception:
                pass

        # Update latest KhataFollowup or create one
        followup = (
            self.db.query(KhataFollowup)
            .filter(
                KhataFollowup.tenant_id == self.tenant_id,
                KhataFollowup.customer_id == customer.id,
            )
            .order_by(KhataFollowup.id.desc())
            .first()
        )

        status_map = {
            "promise_to_pay": "promised",
            "already_paid": "paid",
            "dispute": "disputed",
            "delay": "promised",
        }
        new_status = status_map.get(intent, "reminder_sent")

        if followup:
            followup.customer_reply = reply_text
            followup.detected_intent = intent
            followup.promised_date = parsed_date
            followup.status = new_status
            followup.notes = f"AI Classified: {intent}. Promised: {parsed_date}"
        else:
            followup = KhataFollowup(
                tenant_id=self.tenant_id,
                store_id=self.store_id,
                customer_id=customer.id,
                outstanding_amount=customer.outstanding_balance,
                reminder_sent_at=datetime.utcnow(),
                customer_reply=reply_text,
                detected_intent=intent,
                promised_date=parsed_date,
                status=new_status,
                notes=f"Inbound reply processed. Intent: {intent}",
            )
            self.db.add(followup)

        self.db.commit()
        self.db.refresh(followup)

        # Send acknowledgment WhatsApp message back to customer
        wa_service = WhatsAppService(db=self.db, tenant_id=self.tenant_id, store_id=self.store_id)
        wa_res = wa_service.send_message(to=customer.phone, message=ack_message)

        return {
            "status": "success",
            "customer_id": customer.id,
            "detected_intent": intent,
            "promised_date": str(parsed_date) if parsed_date else None,
            "followup_status": new_status,
            "acknowledgment_reply": ack_message,
            "whatsapp_result": wa_res,
        }
