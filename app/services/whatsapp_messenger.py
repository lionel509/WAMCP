import httpx
import logging
import json
from typing import Optional, Dict, Any, Literal
from app.config import settings

logger = logging.getLogger(__name__)

class WhatsAppMessenger:
    """
    High-level interface for sending WhatsApp messages via Meta Graph API.
    Supports text messages, templates, and media.
    """
    
    def __init__(self):
        self.api_token = settings.whatsapp_access_token
        self.api_version = settings.whatsapp_api_version
        self.base_url = settings.whatsapp_base_url
        self.phone_number_id = settings.whatsapp_phone_number_id
        
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with auth."""
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers
    
    def _is_placeholder_phone_id(self, phone_id: Optional[str]) -> bool:
        """Check if phone_id is a placeholder value."""
        if not phone_id:
            return True
        normalized = str(phone_id).strip().lower()
        return normalized in ("string", "replace_me", "todo", "changeme") or normalized.startswith("your_")
    
    def _log_graph_error(self, status_code: int, response_text: str, context: str = "") -> Dict[str, Any]:
        """
        Parse and log Meta Graph API error responses.
        
        Returns a structured error dict.
        """
        error_dict = {
            "error": "graph_api_error",
            "status_code": status_code,
            "details": {}
        }
        
        try:
            response_json = json.loads(response_text)
            error_dict["details"] = response_json.get("error", response_json)
            
            # Log the structured error
            error_payload = response_json.get("error", {})
            if isinstance(error_payload, dict):
                error_msg = error_payload.get("message", "Unknown error")
                error_code = error_payload.get("code", "")
                fbtrace_id = error_payload.get("fbtrace_id", "")
                
                log_msg = f"Meta Graph API error ({status_code})"
                if context:
                    log_msg += f" [{context}]"
                log_msg += f": {error_msg}"
                if error_code:
                    log_msg += f" (code: {error_code})"
                if fbtrace_id:
                    log_msg += f" (fbtrace_id: {fbtrace_id})"
                
                logger.error(log_msg)
            else:
                logger.error(f"Meta Graph API error ({status_code}): {response_json}")
        except (json.JSONDecodeError, KeyError):
            logger.error(f"Meta Graph API error ({status_code}): {response_text}")
            error_dict["details"] = {"raw_response": response_text}
        
        return error_dict
    
    async def send_text(
        self,
        to: str,
        body: str,
        preview_url: bool = False,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a text message.
        
        Args:
            to: Recipient phone number (e.g., "15169007810")
            body: Message text
            preview_url: Enable URL preview
            phone_number_id: Override default phone number ID
        """
        if not self.api_token:
            return {"error": "WhatsApp access token not configured", "error_type": "missing_token"}
        
        phone_id = phone_number_id or self.phone_number_id
        if not phone_id:
            return {"error": "WhatsApp phone number ID not configured", "error_type": "missing_phone_id"}
        
        if self._is_placeholder_phone_id(phone_id):
            return {
                "error": f"WHATSAPP_PHONE_NUMBER_ID is configured to placeholder '{phone_id}'. Check your .env file and set it to your actual phone number ID from Meta.",
                "error_type": "placeholder_config"
            }
        
        # Validate 'to' parameter is not a placeholder
        if self._is_placeholder_phone_id(to):
            return {
                "error": f"Recipient 'to' parameter is set to placeholder '{to}'. Must be a valid E.164 phone number like '15169007810'.",
                "error_type": "invalid_recipient"
            }
        
        url = f"{self.base_url}/{self.api_version}/{phone_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body, "preview_url": preview_url}
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=self._get_headers(), json=payload, timeout=10.0)
                
                if response.status_code >= 400:
                    return self._log_graph_error(response.status_code, response.text, context="send_text")
                
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to send text message: {e}")
            return {"error": str(e), "error_type": "http_error"}
    
    async def send_template(
        self,
        to: str,
        template_name: str,
        language_code: str = "en_US",
        parameters: Optional[list] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a template message.
        
        Args:
            to: Recipient phone number
            template_name: Template name (e.g., "hello_world")
            language_code: Language code (default: "en_US")
            parameters: Template parameter values
            phone_number_id: Override default phone number ID
        """
        if not self.api_token:
            return {"error": "WhatsApp access token not configured", "error_type": "missing_token"}
        
        phone_id = phone_number_id or self.phone_number_id
        if not phone_id:
            return {"error": "WhatsApp phone number ID not configured", "error_type": "missing_phone_id"}
        
        if self._is_placeholder_phone_id(phone_id):
            return {
                "error": f"WHATSAPP_PHONE_NUMBER_ID is configured to placeholder '{phone_id}'. Check your .env file and set it to your actual phone number ID from Meta.",
                "error_type": "placeholder_config"
            }
        
        # Validate 'to' parameter is not a placeholder
        if self._is_placeholder_phone_id(to):
            return {
                "error": f"Recipient 'to' parameter is set to placeholder '{to}'. Must be a valid E.164 phone number like '15169007810'.",
                "error_type": "invalid_recipient"
            }
        
        url = f"{self.base_url}/{self.api_version}/{phone_id}/messages"
        
        template_obj = {
            "name": template_name,
            "language": {"code": language_code}
        }
        
        if parameters:
            template_obj["parameters"] = {"body": parameters}
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": template_obj
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=self._get_headers(), json=payload, timeout=10.0)
                
                if response.status_code >= 400:
                    return self._log_graph_error(response.status_code, response.text, context="send_template")
                
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to send template message: {e}")
            return {"error": str(e), "error_type": "http_error"}
    
    async def send_media(
        self,
        to: str,
        media_type: Literal["image", "document", "audio", "video"],
        media_url: str,
        caption: Optional[str] = None,
        phone_number_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a media message.
        
        Args:
            to: Recipient phone number
            media_type: Type of media (image, document, audio, video)
            media_url: URL to the media file
            caption: Optional caption
            phone_number_id: Override default phone number ID
        """
        if not self.api_token:
            return {"error": "WhatsApp access token not configured", "error_type": "missing_token"}
        
        phone_id = phone_number_id or self.phone_number_id
        if not phone_id:
            return {"error": "WhatsApp phone number ID not configured", "error_type": "missing_phone_id"}
        
        if self._is_placeholder_phone_id(phone_id):
            return {
                "error": f"WHATSAPP_PHONE_NUMBER_ID is configured to placeholder '{phone_id}'. Check your .env file and set it to your actual phone number ID from Meta.",
                "error_type": "placeholder_config"
            }
        
        # Validate 'to' parameter is not a placeholder
        if self._is_placeholder_phone_id(to):
            return {
                "error": f"Recipient 'to' parameter is set to placeholder '{to}'. Must be a valid E.164 phone number like '15169007810'.",
                "error_type": "invalid_recipient"
            }
        
        url = f"{self.base_url}/{self.api_version}/{phone_id}/messages"
        
        media_obj = {"link": media_url}
        if caption and media_type in ["image", "document", "video"]:
            media_obj["caption"] = caption
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": media_type,
            media_type: media_obj
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=self._get_headers(), json=payload, timeout=10.0)
                
                if response.status_code >= 400:
                    return self._log_graph_error(response.status_code, response.text, context="send_media")
                
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to send media message: {e}")
            return {"error": str(e), "error_type": "http_error"}


# Global instance
messenger = WhatsAppMessenger()
