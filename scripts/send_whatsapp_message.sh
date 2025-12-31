#!/bin/bash

# Helper script to send a WhatsApp message via Meta Graph API
# Usage: ./scripts/send_whatsapp_message.sh [phone_number] [template_name]
# Example: ./scripts/send_whatsapp_message.sh 15169007810 hello_world

set -e

# Load environment variables
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found. Run this from the repo root."
    exit 1
fi

source .env

# Defaults
PHONE_NUMBER="${1:-${DEBUG_ECHO_ALLOWLIST_E164}}"
TEMPLATE_NAME="${2:-hello_world}"
LANGUAGE_CODE="${3:-en_US}"

# Validation
if [ -z "$PHONE_NUMBER" ]; then
    echo "❌ Error: No phone number provided."
    echo "Usage: $0 <phone_number> [template_name] [language_code]"
    echo ""
    echo "Example: $0 15169007810 hello_world en_US"
    exit 1
fi

if [ -z "$WHATSAPP_ACCESS_TOKEN" ]; then
    echo "❌ Error: WHATSAPP_ACCESS_TOKEN not set in .env"
    exit 1
fi

if [ -z "$WHATSAPP_PHONE_NUMBER_ID" ]; then
    echo "❌ Error: WHATSAPP_PHONE_NUMBER_ID not set in .env"
    exit 1
fi

# API endpoint
ENDPOINT="https://graph.facebook.com/v22.0/${WHATSAPP_PHONE_NUMBER_ID}/messages"

# Build JSON payload
PAYLOAD=$(cat <<EOF
{
  "messaging_product": "whatsapp",
  "to": "$PHONE_NUMBER",
  "type": "template",
  "template": {
    "name": "$TEMPLATE_NAME",
    "language": {
      "code": "$LANGUAGE_CODE"
    }
  }
}
EOF
)

echo "📤 Sending WhatsApp message..."
echo "   Phone Number ID: $WHATSAPP_PHONE_NUMBER_ID"
echo "   Recipient: +$PHONE_NUMBER"
echo "   Template: $TEMPLATE_NAME"
echo "   Language: $LANGUAGE_CODE"
echo ""

# Send the message
curl -i -X POST "$ENDPOINT" \
  -H "Authorization: Bearer $WHATSAPP_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD"

echo ""
echo "✅ Request sent."
