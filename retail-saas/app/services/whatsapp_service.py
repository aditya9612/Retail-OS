import httpx

from app.core.config import get_settings

settings = get_settings()


class WhatsAppService:
    def __init__(self):
        self.api_url = settings.WHATSAPP_API_URL
        self.token = settings.WHATSAPP_API_TOKEN
        self.phone_id = settings.WHATSAPP_PHONE_NUMBER_ID

    async def send_message(self, to: str, message: str) -> dict:
        if not self.api_url or not self.token:
            return {"status": "skipped", "reason": "WhatsApp not configured", "to": to, "message": message}
        url = f"{self.api_url}/{self.phone_id}/messages"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message},
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=30)
            return {"status": response.status_code, "data": response.json()}

    async def send_order_confirmation(self, phone: str, order_number: str, total: str) -> dict:
        message = f"Your order {order_number} has been confirmed. Total: Rs.{total}. Thank you for shopping with us!"
        return await self.send_message(phone, message)

    async def send_invoice(self, phone: str, invoice_number: str, pdf_url: str) -> dict:
        message = f"Invoice {invoice_number} is ready. Download: {pdf_url}"
        return await self.send_message(phone, message)

    async def send_promotional(self, phone: str, campaign_message: str) -> dict:
        return await self.send_message(phone, campaign_message)

    def handle_webhook(self, payload: dict) -> dict:
        return {"status": "received", "entries": payload.get("entry", [])}
