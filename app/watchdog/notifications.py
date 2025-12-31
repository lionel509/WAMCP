import logging
import json
from app.config import settings
from app.integrations.whatsapp_client import whatsapp_client
import redis
import asyncio

logger = logging.getLogger(__name__)

# Redis for Rate Limiting notifications
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

async def send_alert(alert_name: str, details: dict):
    """
    Log alert and optionally notify admin via WhatsApp.
    """
    msg = f"WATCHDOG ALERT: {alert_name}. Details: {json.dumps(details)}"
    logger.error(msg)
    
    if settings.WATCHDOG_NOTIFY_MODE == "admin_whatsapp_debug":
        if not settings.debug_echo_mode:
            logger.info("Watchdog notification skipped (DEBUG_ECHO_MODE=false)")
            return
            
        admin_phone = settings.WATCHDOG_ADMIN_NOTIFY_E164
        if not admin_phone:
            logger.info("Watchdog notification skipped (No admin phone configured)")
            return
            
        # Check Allowlist
        allowed_numbers = settings.debug_echo_allowlist_e164
        if admin_phone not in allowed_numbers:
             logger.warning(f"Watchdog admin phone {admin_phone} not in Allowlist. Skipping.")
             return
             
        # Rate Limit (1 notification per alert type per 30 mins?)
        # Or global rate limit?
        # Let's rate limit per alert_name to avoid spamming.
        key = f"watchdog:notify:{alert_name}"
        if redis_client.set(key, "1", ex=300, nx=True): # 5 minutes cooldown
             try:
                 # We need business phone ID to send FROM.
                 # Ideally config has it. 
                 # Since we lack it in config, we might need to add it or fetch it.
                 # For now, if we don't have it, we can't send.
                 # Assuming whatsapp_client handles mapping or we added config.
                 # I'll use a placeholder or check if settings has it.
                 # Actually, `send_text_message` requires `phone_number_id`.
                 # Preferred: use configured business phone number id if available.
                 pid = settings.whatsapp_phone_number_id
                 if pid:
                     await whatsapp_client.send_text_message(pid, admin_phone, msg)
                 else:
                     logger.warning("Watchdog notification skipped (WHATSAPP_PHONE_NUMBER_ID not configured)")
             except Exception as e:
                 logger.error(f"Failed to send watchdog notification: {e}")
        else:
             logger.info(f"Watchdog notification rate limited for {alert_name}")
