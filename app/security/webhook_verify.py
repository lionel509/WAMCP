import hmac
import hashlib
import logging

logger = logging.getLogger(__name__)

def verify_signature(raw_body: bytes, signature_header: str, app_secret: str) -> bool:
    """
    Verifies the X-Hub-Signature-256 header.
    Format: sha256=<sig>
    """
    if not signature_header or not app_secret:
        return False
    
    parts = signature_header.split("=")
    if len(parts) != 2 or parts[0] != "sha256":
        logger.warning(f"Invalid signature header format: {signature_header}")
        return False
        
    sig = parts[1]
    
    # Calculate expected signature
    calculated_hmac = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(calculated_hmac, sig)
