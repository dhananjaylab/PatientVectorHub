#!/usr/bin/env bash
# scripts/vault_init.sh — Seed Vault dev server with all required secrets
# Called automatically by: make vault-init / make dev
set -euo pipefail

export VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
export VAULT_TOKEN="${VAULT_TOKEN:-dev-root-token}"

echo "  Connecting to Vault at $VAULT_ADDR..."

# Wait until Vault is responding
for i in $(seq 1 20); do
  if vault status -address="$VAULT_ADDR" > /dev/null 2>&1; then break; fi
  echo "  Waiting for Vault... ($i/20)"
  sleep 3
done

# Enable KV v2 (idempotent)
vault secrets enable -path=secret kv-v2 2>/dev/null || true

# Enable Transit engine for PHI encryption (idempotent)
vault secrets enable transit 2>/dev/null || true

# Create PHI encryption key (aes256-gcm96)
vault write -f transit/keys/phi-key type=aes256-gcm96 2>/dev/null || true
echo "  ✓ Transit key: phi-key"

# Seed LLM API keys
vault kv put secret/llm/anthropic \
  api_key="${ANTHROPIC_API_KEY:-sk-ant-placeholder}" > /dev/null
vault kv put secret/llm/openai \
  api_key="${OPENAI_API_KEY:-sk-placeholder}" > /dev/null
vault kv put secret/llm/gemini \
  api_key="${GEMINI_API_KEY:-AIza-placeholder}" > /dev/null
echo "  ✓ LLM keys stored: anthropic, openai, gemini"

# Seed database credentials
vault kv put secret/db/postgres \
  user=pvh \
  password=pvh_local \
  host=localhost \
  port=5432 \
  database=pvh > /dev/null
echo "  ✓ DB credentials stored"

# Create application policy
vault policy write pvh-app - << 'POLICY'
path "transit/encrypt/phi-key"  { capabilities = ["update"] }
path "transit/decrypt/phi-key"  { capabilities = ["update"] }
path "secret/data/llm/+"        { capabilities = ["read"] }
path "secret/data/db/+"         { capabilities = ["read"] }
POLICY
echo "  ✓ pvh-app policy written"

echo "  Vault initialisation complete."
