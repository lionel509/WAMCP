import httpx
import logging
from typing import Optional, Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)

class WhatsAppClient:
    def __init__(self):
        self.api_token = settings.whatsapp_access_token
        self.api_version = settings.whatsapp_api_version
        self.base_url = settings.whatsapp_base_url
        self.default_phone_number_id = settings.whatsapp_phone_number_id
        self.headers = {
            "Content-Type": "application/json"
        }
        if self.api_token:
            self.headers["Authorization"] = f"Bearer {self.api_token}"

    async def send_text_message(
        self,
        phone_number_id: Optional[str],
        to: str,
        body: str,
        preview_url: bool = False,
    ) -> Dict[str, Any]:
        """
        Send a text message to a user or group.
        'to' should be the phone number (individual) or group ID (if supported).
        """
        if not self.api_token:
            logger.warning("WhatsApp access token not configured. Skipping send.")
            return {"error": "no_token"}

        active_phone_number_id = phone_number_id or self.default_phone_number_id
        if not active_phone_number_id:
            logger.warning("WhatsApp phone number ID missing. Skipping send.")
            return {"error": "no_phone_number_id"}

        url = f"{self.base_url}/{self.api_version}/{active_phone_number_id}/messages"
        recipient_type = "group" if "@g.us" in to else "individual"

        payload = {
            "messaging_product": "whatsapp",
            # WA Cloud API defaults to individual; set explicitly so group IDs work too.
            "recipient_type": recipient_type,
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
