import pytest
import httpx
import uuid
import json
import hashlib
import os

# Configuration
API_URL = os.getenv("API_URL", "http://api:8000") # Default to docker service name
APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "secret") # Default match dev

@pytest.mark.asyncio
async def test_smoke_webhook_ingestion():
    """
    End-to-end smoke test: Send webhook -> Check 200 OK.
    """
    webhook_url = f"{API_URL}/webhooks/whatsapp"
    
    # Payload
    body = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "999", "display_phone_number": "999"},
                    "messages": [{
                        "from": "888",
                        "id": f"wamid.SMOKE_{uuid.uuid4()}",
                        "timestamp": "1700000000",
                        "type": "text",
                        "text": {"body": "Smoke Test Message"}
                    }]
                }
            }]
        }]
    }
    raw_body = json.dumps(body).encode()
    
    # Signature
    hmac_obj = hashlib.sha256(raw_body) # Just hash for verify? 
    # Verification needs HMAC-SHA256 using SECRET
    import hmac
    sig = hmac.new(APP_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    headers = {"x-hub-signature-256": f"sha256={sig}"}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Check Health first
        try:
            resp = await client.get(f"{API_URL}/health")
            if resp.status_code != 200:
                pytest.skip(f"API not healthy: {resp.status_code}")
        except httpx.ConnectError:
             pytest.skip("API not accessible (stack might be down)")

        # Send Webhook
        resp = await client.post(webhook_url, content=raw_body, headers=headers)
        
        assert resp.status_code == 200, f"Webhook failed: {resp.text}"
        data = resp.json()
        assert data["status"] == "processed"
        assert data["count"] == 1

@pytest.mark.asyncio
async def test_smoke_watchdog_status():
    """
    Check if Watchdog admin endpoint is reachable and returns list.
    """
    admin_key = os.getenv("ADMIN_API_KEY", "admin123")
    url = f"{API_URL}/admin/watchdog/status"
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params={"api_key": admin_key})
        
        # If 403, check key. Default is admin123.
        if resp.status_code == 403:
             pytest.fail("Admin API Key rejected")
             
        assert resp.status_code == 200, f"Admin Watchdog Status failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, list)
