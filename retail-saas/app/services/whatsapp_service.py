import json
import re
from typing import Optional, List, Dict, Any
import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logger import logger
from app.models.whatsapp import WhatsAppSetting, WhatsAppLog
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.customer import Customer
from app.models.store import Store

settings = get_settings()


def normalize_whatsapp_phone(phone: str, default_country: str = "91") -> str:
    """Normalizes phone numbers to Meta WhatsApp E.164 digit string without + prefix.
    E.g. 9876543210 -> 919876543210
         +91 98765-43210 -> 919876543210
         +1 (555) 019-2831 -> 15550192831
    """
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone).lstrip("0")
    if not digits:
        return ""
    if len(digits) == 10:
        return f"{default_country}{digits}"
    return digits


class WhatsAppService:
    def __init__(
        self,
        db: Optional[Session] = None,
        tenant_id: Optional[int] = None,
        store_id: Optional[int] = None,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.store_id = store_id
        self._load_config()

    def _load_config(self) -> None:
        """Loads credentials from Tenant WhatsAppSetting or defaults to system settings."""
        self.api_url = (settings.WHATSAPP_API_URL or "https://graph.facebook.com/v19.0").rstrip("/")
        self.token = settings.WHATSAPP_API_TOKEN or ""
        self.phone_id = settings.WHATSAPP_PHONE_NUMBER_ID or ""
        self.waba_id = settings.WHATSAPP_BUSINESS_ACCOUNT_ID or ""
        self.webhook_verify_token = settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN or "retail_os_webhook_verify_token"
        self.is_enabled = True
        self.auto_send_invoice = True
        self.auto_send_order_confirm = True
        self.template_invoice = "pos_invoice_receipt"
        self.template_order_confirm = "order_confirmation"
        self.template_language = "en_US"

        if self.db and self.tenant_id:
            try:
                query = self.db.query(WhatsAppSetting).filter(WhatsAppSetting.tenant_id == self.tenant_id)
                setting = None
                if self.store_id:
                    setting = query.filter(WhatsAppSetting.store_id == self.store_id).first()
                if not setting:
                    setting = query.filter(WhatsAppSetting.store_id.is_(None)).first()

                if setting:
                    if setting.phone_number_id:
                        self.phone_id = setting.phone_number_id
                    if setting.access_token:
                        self.token = setting.access_token
                    if setting.business_account_id:
                        self.waba_id = setting.business_account_id
                    if setting.webhook_verify_token:
                        self.webhook_verify_token = setting.webhook_verify_token
                    self.is_enabled = setting.is_enabled
                    self.auto_send_invoice = setting.auto_send_invoice
                    self.auto_send_order_confirm = setting.auto_send_order_confirm
                    if setting.template_invoice:
                        self.template_invoice = setting.template_invoice
                    if setting.template_order_confirm:
                        self.template_order_confirm = setting.template_order_confirm
                    if setting.template_language:
                        self.template_language = setting.template_language
            except Exception as exc:
                logger.warning("Could not load WhatsAppSetting for tenant %s: %s", self.tenant_id, exc)

    @property
    def is_configured(self) -> bool:
        return bool(self.api_url and self.token and self.phone_id and self.is_enabled)

    # -------------------------------------------------------------
    # Low-Level Meta Cloud API Transports
    # -------------------------------------------------------------

    def send_raw_payload_sync(self, payload: dict) -> dict:
        """Sends a JSON payload directly to Meta WhatsApp Cloud API endpoint (Synchronous)."""
        if not self.is_configured:
            return {
                "status": "skipped",
                "reason": "WhatsApp service not configured or disabled",
                "phone_id": self.phone_id,
                "payload": payload,
            }

        url = f"{self.api_url}/{self.phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, json=payload, headers=headers)
                status_code = response.status_code
                try:
                    data = response.json()
                except Exception:
                    data = {"text": response.text}

                if 200 <= status_code < 300:
                    message_id = None
                    if "messages" in data and len(data["messages"]) > 0:
                        message_id = data["messages"][0].get("id")
                    return {
                        "status": "success",
                        "status_code": status_code,
                        "message_id": message_id,
                        "data": data,
                    }
                else:
                    logger.error("Meta WhatsApp Cloud API Error (%s): %s", status_code, data)
                    return {
                        "status": "failed",
                        "status_code": status_code,
                        "error": data,
                    }
        except Exception as exc:
            logger.error("Meta WhatsApp Cloud API Request Exception: %s", exc)
            return {
                "status": "failed",
                "error": str(exc),
            }

    async def send_raw_payload_async(self, payload: dict) -> dict:
        """Sends a JSON payload asynchronously to Meta WhatsApp Cloud API endpoint."""
        if not self.is_configured:
            return {
                "status": "skipped",
                "reason": "WhatsApp service not configured or disabled",
                "phone_id": self.phone_id,
                "payload": payload,
            }

        url = f"{self.api_url}/{self.phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                status_code = response.status_code
                try:
                    data = response.json()
                except Exception:
                    data = {"text": response.text}

                if 200 <= status_code < 300:
                    message_id = None
                    if "messages" in data and len(data["messages"]) > 0:
                        message_id = data["messages"][0].get("id")
                    return {
                        "status": "success",
                        "status_code": status_code,
                        "message_id": message_id,
                        "data": data,
                    }
                else:
                    return {
                        "status": "failed",
                        "status_code": status_code,
                        "error": data,
                    }
        except Exception as exc:
            return {
                "status": "failed",
                "error": str(exc),
            }

    # -------------------------------------------------------------
    # Message Format Builders
    # -------------------------------------------------------------

    def build_template_payload(
        self,
        to_phone: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[List[Dict[str, Any]]] = None,
    ) -> dict:
        """Constructs a Meta Cloud API Template Message payload."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalize_whatsapp_phone(to_phone),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }
        if components:
            payload["template"]["components"] = components
        return payload

    def build_document_payload(
        self,
        to_phone: str,
        document_url: str,
        filename: str,
        caption: Optional[str] = None,
    ) -> dict:
        """Constructs a Meta Cloud API Document/PDF message payload."""
        doc_obj: Dict[str, Any] = {
            "link": document_url,
            "filename": filename,
        }
        if caption:
            doc_obj["caption"] = caption

        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalize_whatsapp_phone(to_phone),
            "type": "document",
            "document": doc_obj,
        }

    def build_text_payload(
        self,
        to_phone: str,
        message: str,
        preview_url: bool = False,
    ) -> dict:
        """Constructs a Meta Cloud API plain text message payload."""
        return {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalize_whatsapp_phone(to_phone),
            "type": "text",
            "text": {
                "preview_url": preview_url,
                "body": message,
            },
        }

    # -------------------------------------------------------------
    # High-Level Business Messaging
    # -------------------------------------------------------------

    def send_invoice_notification(
        self,
        invoice: Invoice,
        recipient_phone: Optional[str] = None,
        custom_note: Optional[str] = None,
    ) -> dict:
        """Sends an invoice to customer's WhatsApp with PDF attachment/link and logs result."""
        target_phone = recipient_phone
        customer_name = "Valued Customer"

        if not target_phone and invoice.order and invoice.order.customer:
            cust = invoice.order.customer
            if getattr(cust, "whatsapp_opt_in", True) is False:
                return {"status": "skipped", "reason": "Customer opted out of WhatsApp"}
            target_phone = cust.phone
            customer_name = cust.name or customer_name
        elif not target_phone and self.db and invoice.customer_id:
            cust = self.db.query(Customer).filter(Customer.id == invoice.customer_id).first()
            if cust:
                if getattr(cust, "whatsapp_opt_in", True) is False:
                    return {"status": "skipped", "reason": "Customer opted out of WhatsApp"}
                target_phone = cust.phone
                customer_name = cust.name or customer_name

        if not target_phone:
            return {"status": "skipped", "reason": "No recipient phone number found for invoice"}

        store_name = "Retail Store"
        if invoice.store and invoice.store.name:
            store_name = invoice.store.name
        elif self.db and invoice.store_id:
            s = self.db.query(Store).filter(Store.id == invoice.store_id).first()
            if s and s.name:
                store_name = s.name

        # Resolve public PDF link
        base_url = settings.APP_BASE_URL.rstrip("/")
        if invoice.pdf_url and invoice.pdf_url.startswith("http"):
            pdf_link = invoice.pdf_url
        else:
            pdf_link = f"{base_url}/api/v1/invoices/{invoice.id}/pdf"

        filename = f"Invoice_{invoice.invoice_number}.pdf"
        amount_str = f"Rs.{float(invoice.total_amount):,.2f}"

        # Strategy 1: Attempt approved Template with Header Document
        components = [
            {
                "type": "header",
                "parameters": [
                    {
                        "type": "document",
                        "document": {
                            "link": pdf_link,
                            "filename": filename,
                        },
                    }
                ],
            },
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": customer_name},
                    {"type": "text", "text": invoice.invoice_number},
                    {"type": "text", "text": amount_str},
                    {"type": "text", "text": store_name},
                ],
            },
        ]
        template_payload = self.build_template_payload(
            to_phone=target_phone,
            template_name=self.template_invoice,
            language_code=self.template_language,
            components=components,
        )

        res = self.send_raw_payload_sync(template_payload)

        # Strategy 2 Fallback: If template is not registered or fails, send as direct document or text link
        if res.get("status") == "failed":
            error_data = res.get("error", {})
            err_msg = json.dumps(error_data) if isinstance(error_data, dict) else str(error_data)
            logger.info("Template dispatch failed, attempting direct document fallback: %s", err_msg)

            caption = (
                f"🧾 Invoice {invoice.invoice_number} from {store_name}\n"
                f"Dear {customer_name}, your bill of {amount_str} is ready. Thank you for your purchase!"
            )
            if custom_note:
                caption += f"\nNote: {custom_note}"

            doc_payload = self.build_document_payload(
                to_phone=target_phone,
                document_url=pdf_link,
                filename=filename,
                caption=caption,
            )
            fallback_res = self.send_raw_payload_sync(doc_payload)
            if fallback_res.get("status") == "success":
                res = fallback_res
            else:
                # Strategy 3 Fallback: Plain text with download link
                text_msg = (
                    f"🧾 *{store_name}* - Invoice {invoice.invoice_number}\n"
                    f"Hello {customer_name}, your purchase total is *{amount_str}*.\n"
                    f"Download your tax invoice: {pdf_link}\n"
                    f"Thank you for shopping with us!"
                )
                text_payload = self.build_text_payload(
                    to_phone=target_phone,
                    message=text_msg,
                    preview_url=True,
                )
                res = self.send_raw_payload_sync(text_payload)

        # Record to WhatsAppLog
        self._record_log(
            recipient_phone=normalize_whatsapp_phone(target_phone),
            message_type="invoice",
            template_name=self.template_invoice,
            invoice_id=invoice.id,
            result=res,
        )

        return res

    def send_order_confirmation(
        self,
        phone: str,
        order_number: str,
        total: str,
        store_name: str = "Retail Store",
    ) -> dict:
        """Sends an order confirmation message."""
        target_phone = normalize_whatsapp_phone(phone)
        amount_str = f"Rs.{total}"

        # Template attempt
        components = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": order_number},
                    {"type": "text", "text": amount_str},
                    {"type": "text", "text": store_name},
                ],
            }
        ]
        template_payload = self.build_template_payload(
            to_phone=target_phone,
            template_name=self.template_order_confirm,
            language_code=self.template_language,
            components=components,
        )
        res = self.send_raw_payload_sync(template_payload)

        # Fallback to text
        if res.get("status") == "failed":
            text_msg = (
                f"✅ *Order Confirmed!*\n"
                f"Your order #{order_number} for {amount_str} at *{store_name}* has been confirmed.\n"
                f"Thank you for shopping with us!"
            )
            text_payload = self.build_text_payload(
                to_phone=target_phone,
                message=text_msg,
            )
            res = self.send_raw_payload_sync(text_payload)

        self._record_log(
            recipient_phone=target_phone,
            message_type="order_confirmation",
            template_name=self.template_order_confirm,
            result=res,
        )
        return res

    def send_message(self, to: str, message: str) -> dict:
        """Sends a freeform text message (for backward compatibility)."""
        payload = self.build_text_payload(to, message)
        res = self.send_raw_payload_sync(payload)
        self._record_log(
            recipient_phone=normalize_whatsapp_phone(to),
            message_type="custom",
            template_name=None,
            result=res,
        )
        return res

    async def send_message_async(self, to: str, message: str) -> dict:
        """Async version of send_message."""
        payload = self.build_text_payload(to, message)
        return await self.send_raw_payload_async(payload)

    def send_invoice(self, phone: str, invoice_number: str, pdf_url: str) -> dict:
        """Sends an invoice download link message (legacy signature)."""
        message = f"Your invoice {invoice_number} is ready. Download: {pdf_url}"
        return self.send_message(phone, message)

    def send_promotional(self, phone: str, campaign_message: str) -> dict:
        return self.send_message(phone, campaign_message)

    # -------------------------------------------------------------
    # Webhooks & Receipts
    # -------------------------------------------------------------

    def verify_webhook(self, mode: Optional[str], token: Optional[str], challenge: Optional[str]) -> Optional[str]:
        """Validates Meta Cloud API Webhook handshake request."""
        if mode == "subscribe" and token == self.webhook_verify_token:
            return challenge
        return None

    def handle_webhook(self, payload: dict) -> dict:
        """Processes incoming Meta Cloud API delivery updates and inbound customer messages."""
        entries = payload.get("entry", [])
        updated_count = 0

        if not self.db:
            return {"status": "received", "entries_count": len(entries)}

        try:
            for entry in entries:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    # Delivery Status Updates: sent, delivered, read, failed
                    for status_item in value.get("statuses", []):
                        meta_id = status_item.get("id")
                        new_status = status_item.get("status")
                        if meta_id and new_status:
                            log_entry = (
                                self.db.query(WhatsAppLog)
                                .filter(WhatsAppLog.meta_message_id == meta_id)
                                .first()
                            )
                            if log_entry:
                                log_entry.status = new_status
                                if new_status == "failed" and "errors" in status_item:
                                    log_entry.error_message = json.dumps(status_item["errors"])
                                updated_count += 1

            if updated_count > 0:
                self.db.commit()
        except Exception as exc:
            logger.error("Error processing Meta WhatsApp webhook: %s", exc)
            self.db.rollback()

        return {"status": "success", "updated_statuses": updated_count}

    # -------------------------------------------------------------
    # Internal Helper: Logging
    # -------------------------------------------------------------

    def _record_log(
        self,
        recipient_phone: str,
        message_type: str,
        template_name: Optional[str],
        result: dict,
        invoice_id: Optional[int] = None,
        order_id: Optional[int] = None,
    ) -> None:
        if not self.db or not self.tenant_id:
            return

        try:
            status = "sent" if result.get("status") == "success" else "failed"
            error_msg = None
            if status == "failed":
                err = result.get("error") or result.get("reason")
                error_msg = json.dumps(err) if isinstance(err, (dict, list)) else str(err)

            log_entry = WhatsAppLog(
                tenant_id=self.tenant_id,
                store_id=self.store_id,
                recipient_phone=recipient_phone,
                message_type=message_type,
                template_name=template_name,
                meta_message_id=result.get("message_id"),
                status=status,
                error_message=error_msg,
                invoice_id=invoice_id,
                order_id=order_id,
                payload_snapshot=result.get("data"),
            )
            self.db.add(log_entry)
            self.db.commit()
        except Exception as exc:
            logger.warning("Could not record WhatsAppLog: %s", exc)
            try:
                self.db.rollback()
            except Exception:
                pass
