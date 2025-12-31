import httpx
import logging
from typing import Optional, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)

class WhatsAppClient:
    def __init__(self):
        self.api_token = settings.WHATSAPP_API_TOKEN
        self.base_url = "https://graph.facebook.com/v21.0" # Version might need update
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

    async def send_text_message(self, phone_number_id: str, to: str, body: str, preview_url: bool = False) -> Dict[str, Any]:
        """
        Send a text message to a user or group.
        'to' should be the phone number (individual) or group ID (if supported).
        """
        if not self.api_token:
            logger.warning("WhatsApp API Token not configured. Skipping send.")
            return {"error": "no_token"}

        url = f"{self.base_url}/{phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recruit_type": "individual", # or group? usually inferred from ID or 'to'
            "to": to,
            "type": "text",
            "text": {
                "body": body,
                "preview_url": preview_url
            }
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, headers=self.headers, json=payload, timeout=10.0)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"Failed to send WhatsApp message: {e}")
                if hasattr(e, "response"):
                    logger.error(f"Response: {e.response.text}")
                return {"error": str(e)}

whatsapp_client = WhatsAppClient()
