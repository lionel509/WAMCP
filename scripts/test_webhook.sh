#!/bin/bash
# Test script for WhatsApp webhook integration
# Usage: ./scripts/test_webhook.sh [action]

set -e

ACTION="${1:-all}"
API_URL="${API_URL:-http://localhost:8000}"
ADMIN_KEY="${ADMIN_KEY:-admin123}"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo_test() {
  echo -e "${BLUE}→ $1${NC}"
}

echo_pass() {
  echo -e "${GREEN}✓ $1${NC}"
}

echo_fail() {
  echo -e "${RED}✗ $1${NC}"
  exit 1
}

# Test 1: Health check
test_health() {
  echo_test "Testing health endpoint..."
  RESPONSE=$(curl -s -w "\n%{http_code}" "$API_URL/healthz")
  STATUS=$(echo "$RESPONSE" | tail -1)
  BODY=$(echo "$RESPONSE" | head -1)
  
  if [ "$STATUS" = "200" ]; then
    echo_pass "Health check passed: $BODY"
  else
    echo_fail "Health check failed (HTTP $STATUS): $BODY"
  fi
}

# Test 2: Webhook verification
test_webhook_verify() {
  echo_test "Testing webhook verification (GET)..."
  CHALLENGE="test_challenge_$(date +%s)"
  RESPONSE=$(curl -s -w "\n%{http_code}" \
    "$API_URL/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=dev-verify-token&hub.challenge=$CHALLENGE")
  STATUS=$(echo "$RESPONSE" | tail -1)
  BODY=$(echo "$RESPONSE" | head -1)
  
  if [ "$STATUS" = "200" ] && [ "$BODY" = "$CHALLENGE" ]; then
    echo_pass "Webhook verification passed: challenge echoed back"
  else
    echo_fail "Webhook verification failed (HTTP $STATUS): expected '$CHALLENGE', got '$BODY'"
  fi
}

# Test 3: Send test message via webhook
test_webhook_receipt() {
  echo_test "Testing webhook receipt (POST)..."
  
  PAYLOAD=$(cat <<'EOF'
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
              "display_phone_number": "15551234567",
              "phone_number_id": "875171289009578"
            },
            "messages": [
              {
                "from": "5169007810",
                "id": "wamid.test.$(date +%s)",
                "timestamp": "$(date +%s)",
                "text": {
                  "body": "Test message from webhook"
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
  
  RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "$API_URL/webhooks/whatsapp" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")
  STATUS=$(echo "$RESPONSE" | tail -1)
  BODY=$(echo "$RESPONSE" | head -1)
  
  if [ "$STATUS" = "200" ]; then
    if echo "$BODY" | grep -q '"ok":true'; then
      echo_pass "Webhook receipt passed: message processed"
    else
      echo_fail "Webhook returned error: $BODY"
    fi
  else
    echo_fail "Webhook receipt failed (HTTP $STATUS): $BODY"
  fi
}

# Test 4: Query conversations
test_query_conversations() {
  echo_test "Testing conversation query..."
  RESPONSE=$(curl -s -w "\n%{http_code}" \
    -H "X-Admin-Api-Key: $ADMIN_KEY" \
    "$API_URL/admin/conversations")
  STATUS=$(echo "$RESPONSE" | tail -1)
  BODY=$(echo "$RESPONSE" | head -1)
  
  if [ "$STATUS" = "200" ]; then
    if echo "$BODY" | grep -q '"conversations"'; then
      COUNT=$(echo "$BODY" | grep -o '"id"' | wc -l)
      echo_pass "Conversation query passed: found $COUNT conversation(s)"
    else
      echo_fail "Invalid response format: $BODY"
    fi
  else
    echo_fail "Conversation query failed (HTTP $STATUS): $BODY"
  fi
}

# Test 5: Verify auth required
test_auth_required() {
  echo_test "Testing authentication requirement..."
  RESPONSE=$(curl -s -w "\n%{http_code}" \
    "$API_URL/admin/conversations")
  STATUS=$(echo "$RESPONSE" | tail -1)
  
  if [ "$STATUS" = "403" ] || [ "$STATUS" = "401" ]; then
    echo_pass "Authentication required: endpoint correctly rejected unauthorized request"
  else
    echo_fail "Authentication not enforced: got HTTP $STATUS instead of 401/403"
  fi
}

# Run tests
case "$ACTION" in
  health)
    test_health
    ;;
  verify)
    test_webhook_verify
    ;;
  receipt)
    test_webhook_receipt
    ;;
  conversations)
    test_query_conversations
    ;;
  auth)
    test_auth_required
    ;;
  all)
    test_health
    test_webhook_verify
    test_webhook_receipt
    test_query_conversations
    test_auth_required
    echo ""
    echo_pass "All tests passed!"
    ;;
  *)
    echo "Usage: $0 [health|verify|receipt|conversations|auth|all]"
    exit 1
    ;;
esac
