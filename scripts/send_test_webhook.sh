#!/bin/bash
# Send a test webhook to the WAMCP API
# Usage: ./send_test_webhook.sh [SECRET] [URL]

SECRET=${1:-"secret"} # Default matches .env.example or test
URL=${2:-"http://localhost:8080/webhooks/whatsapp"}

# Payload
PAYLOAD=$(cat <<EOF
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "123456789",
      "changes": [
        {
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {
              "display_phone_number": "15550001234",
              "phone_number_id": "1234567890"
            },
            "contacts": [
              {
                "profile": {
                  "name": "Test User"
                },
                "wa_id": "16315551111"
              }
            ],
            "messages": [
              {
                "from": "16315551111",
                "id": "wamid.TEST_$(date +%s)",
                "timestamp": "$(date +%s)",
                "text": {
                  "body": "Hello World from Script!"
                },
                "type": "text"
              }
            ]
          },
          "field": "messages"
        }
      ]
    }
  ]
}
EOF
)

# Calculate Signature
# Using python for reliable HMAC
SIG=$(python3 -c "import hmac, hashlib, sys; print('sha256='+hmac.new('$SECRET'.encode(), sys.stdin.read().encode(), hashlib.sha256).hexdigest())" <<< "$PAYLOAD")

echo "Sending Payload to $URL..."
echo "Signature: $SIG"

curl -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: $SIG" \
  -d "$PAYLOAD"

echo -e "\nDone."
