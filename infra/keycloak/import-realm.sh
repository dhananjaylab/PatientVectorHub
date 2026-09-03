#!/bin/bash

# Keycloak realm import script
# This imports the patientvectorhub realm and pvh-spa client

KEYCLOAK_URL=${1:-http://localhost:8080}
ADMIN_USER=${2:-admin}
ADMIN_PASS=${3:-admin}
REALM_FILE="realm.json"

echo "Keycloak Realm Import Script"
echo "============================"
echo "Keycloak URL: $KEYCLOAK_URL"
echo "Realm file: $REALM_FILE"
echo ""

# Step 1: Get admin token
echo "Step 1: Obtaining admin token..."
TOKEN_RESPONSE=$(curl -s -X POST "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=admin-cli&username=$ADMIN_USER&password=$ADMIN_PASS")

TOKEN=$(echo "$TOKEN_RESPONSE" | jq -r '.access_token')

if [ -z "$TOKEN" ] || [ "$TOKEN" == "null" ]; then
    echo "Failed to obtain admin token"
    echo "Response: $TOKEN_RESPONSE"
    exit 1
fi

echo "✓ Token obtained"
echo ""

# Step 2: Import realm
echo "Step 2: Importing realm..."
REALM_JSON=$(cat "$REALM_FILE")

IMPORT_RESPONSE=$(curl -s -X POST "$KEYCLOAK_URL/admin/realms" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "$REALM_JSON" \
  -w "\n%{http_code}")

HTTP_CODE=$(echo "$IMPORT_RESPONSE" | tail -n 1)
RESPONSE_BODY=$(echo "$IMPORT_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" == "201" ] || [ "$HTTP_CODE" == "204" ]; then
    echo "✓ Realm imported successfully"
elif [ "$HTTP_CODE" == "409" ]; then
    echo "ℹ Realm already exists"
else
    echo "Failed with HTTP $HTTP_CODE"
    echo "Response: $RESPONSE_BODY"
    exit 1
fi
echo ""

# Step 3: Verify clients
echo "Step 3: Verifying clients..."
CLIENTS=$(curl -s -X GET "$KEYCLOAK_URL/admin/realms/patientvectorhub/clients" \
  -H "Authorization: Bearer $TOKEN")

PVH_SPA=$(echo "$CLIENTS" | jq '.[] | select(.clientId == "pvh-spa")')

if [ -z "$PVH_SPA" ]; then
    echo "✗ pvh-spa client not found!"
    exit 1
fi

echo "✓ Found pvh-spa client"
CLIENT_ID=$(echo "$PVH_SPA" | jq -r '.id')
echo "  - Client ID: $CLIENT_ID"
echo ""

# Step 4: Verify users
echo "Step 4: Verifying users..."
USERS=$(curl -s -X GET "$KEYCLOAK_URL/admin/realms/patientvectorhub/users" \
  -H "Authorization: Bearer $TOKEN")

USER_COUNT=$(echo "$USERS" | jq 'length')
echo "✓ Found $USER_COUNT users"
echo ""

echo "✅ Realm import completed successfully!"
echo ""
echo "You can now log in with:"
echo "  URL: http://localhost:5173"
echo "  Username: admin@tenant1.test"
echo "  Password: test-password-123"
