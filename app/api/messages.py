from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional, List
from app.services.whatsapp_messenger import messenger
from app.config import settings
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class SendTextRequest(BaseModel):
    to: Optional[str] = None
    body: str
    preview_url: bool = False
    phone_number_id: Optional[str] = None

class SendTemplateRequest(BaseModel):
    to: Optional[str] = None
    template_name: str
    language_code: str = "en_US"
    parameters: Optional[List[str]] = None
    phone_number_id: Optional[str] = None

class SendMediaRequest(BaseModel):
    to: Optional[str] = None
    media_type: str  # "image", "document", "audio", "video"
    media_url: str
    caption: Optional[str] = None
    phone_number_id: Optional[str] = None

def verify_admin_key(x_admin_api_key: str = Header(None)) -> str:
    """Verify admin API key from header."""
    import hmac
    if not x_admin_api_key or not hmac.compare_digest(x_admin_api_key, settings.admin_api_key or ""):
        raise HTTPException(status_code=403, detail="Invalid admin API key")
    return x_admin_api_key

def validate_whatsapp_send_config() -> None:
    """Validate that WhatsApp send config is properly configured."""
    if not settings.whatsapp_access_token:
        raise HTTPException(
            status_code=400,
            detail="WhatsApp is not configured: WHATSAPP_ACCESS_TOKEN is missing"
        )
    if not settings.whatsapp_phone_number_id:
        raise HTTPException(
            status_code=400,
            detail="WhatsApp is not configured: WHATSAPP_PHONE_NUMBER_ID is missing"
        )

@router.post("/send/text")
async def send_text_message(
    req: SendTextRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Send a text message via WhatsApp.
    
    Requires X-Admin-Api-Key header.
    
    Example:
    ```
    curl -X POST http://localhost:8000/send/text \\
      -H "X-Admin-Api-Key: admin123" \\
      -H "Content-Type: application/json" \\
      -d '{
        "to": "15555555555",
        "body": "Hello from WAMCP!"
      }'
    ```
    """
    validate_whatsapp_send_config()
    
    logger.info(f"Sending text message to {req.to}")
    result = await messenger.send_text(
        to=req.to,
        body=req.body,
        preview_url=req.preview_url,
        phone_number_id=req.phone_number_id,
    )
    
    if "error" in result:
        logger.error(f"Failed to send message: {result}")
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result

@router.post("/send/template")
async def send_template_message(
    req: SendTemplateRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Send a template message via WhatsApp.
    
    Requires X-Admin-Api-Key header.
    
    Example:
    ```
    curl -X POST http://localhost:8000/send/template \\
      -H "X-Admin-Api-Key: admin123" \\
      -H "Content-Type: application/json" \\
      -d '{
        "to": "15555555555",
        "template_name": "hello_world",
        "language_code": "en_US"
      }'
    ```
    """
    validate_whatsapp_send_config()
    
    logger.info(f"Sending template '{req.template_name}' to {req.to}")
    result = await messenger.send_template(
        to=req.to,
        template_name=req.template_name,
        language_code=req.language_code,
        parameters=req.parameters,
        phone_number_id=req.phone_number_id,
    )
    
    if "error" in result:
        logger.error(f"Failed to send template: {result}")
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return result

@router.post("/send/media")
async def send_media_message(
    req: SendMediaRequest,
    admin_key: str = Depends(verify_admin_key)
):
    """
    Send a media message (image, document, audio, video) via WhatsApp.
    
    Requires X-Admin-Api-Key header.
    
    Example:
    ```
    curl -X POST http://localhost:8000/send/media \\
      -H "X-Admin-Api-Key: admin123" \\
      -H "Content-Type: application/json" \\
      -d '{
        "to": "15555555555",
        "media_type": "image",
        "media_url": "https://example.com/image.jpg",
        "caption": "Check this out!"
      }'
    ```
    """
    if req.media_type not in ["image", "document", "audio", "video"]:
        raise HTTPException(status_code=400, detail="Invalid media_type")
    
    validate_whatsapp_send_config()
