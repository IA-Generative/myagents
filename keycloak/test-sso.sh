#!/usr/bin/env bash
# Test E2E du SSO Keycloak local : vérifie realm, users, tokens, validation JWT server.
# Usage: ./keycloak/test-sso.sh
set -euo pipefail

KEYCLOAK_URL="http://localhost:${KEYCLOAK_PORT:-8180}"
SERVER_URL="http://localhost:${SERVER_PORT:-8001}"
REALM="myagents"
CLIENT_ID="miraiku-agents"
CLIENT_SECRET="dev-miraiku-agents-secret"

green() { printf "\033[32m✓ %s\033[0m\n" "$1"; }
red()   { printf "\033[31m✗ %s\033[0m\n" "$1"; }
info()  { printf "\033[36m→ %s\033[0m\n" "$1"; }

fail() { red "$1"; exit 1; }

# --- 1. Keycloak realm accessible ---
info "Test 1: Keycloak realm '$REALM' accessible"
DISCOVERY=$(curl -sf "$KEYCLOAK_URL/realms/$REALM/.well-known/openid-configuration" || echo "")
[[ -n "$DISCOVERY" ]] || fail "Realm $REALM non accessible sur $KEYCLOAK_URL"
echo "$DISCOVERY" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['issuer'].endswith('/realms/$REALM')" || fail "Issuer incorrect"
green "Realm accessible, discovery OK"

# --- 2. Token pour admin ---
info "Test 2: Password grant admin/admin"
TOKEN_RESP=$(curl -s "$KEYCLOAK_URL/realms/$REALM/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=$CLIENT_ID" \
  -d "client_secret=$CLIENT_SECRET" \
  -d "username=admin" \
  -d "password=admin" \
  -d "scope=openid profile email" || echo "")
ADMIN_TOKEN=$(echo "$TOKEN_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('access_token',''))" 2>/dev/null || echo "")
[[ -n "$ADMIN_TOKEN" ]] || fail "Pas d'access_token pour admin (resp: $TOKEN_RESP)"
green "Token admin obtenu (len=${#ADMIN_TOKEN})"

# --- 3. Claims du token admin ---
info "Test 3: Claims du token admin (roles, groups, aud)"
echo "$ADMIN_TOKEN" | python3 -c "
import sys, json, base64
t = sys.stdin.read().strip()
p = t.split('.')[1]
p += '=' * (-len(p) % 4)
c = json.loads(base64.urlsafe_b64decode(p))
assert c.get('preferred_username') == 'admin', f'username={c.get(\"preferred_username\")}'
roles = c.get('realm_access', {}).get('roles', [])
assert 'admin' in roles, f'roles={roles}'
groups = c.get('groups', [])
assert 'myagents-admin' in groups, f'groups={groups}'
print(f'  sub: {c.get(\"sub\")}')
print(f'  username: {c.get(\"preferred_username\")}')
print(f'  roles: {roles}')
print(f'  groups: {groups}')
print(f'  aud: {c.get(\"aud\")}')
" || fail "Claims admin incorrects"
green "Claims admin OK (role admin, group myagents-admin)"

# --- 4. Token pour user1 ---
info "Test 4: Password grant user1/user1"
USER_TOKEN=$(curl -s "$KEYCLOAK_URL/realms/$REALM/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=$CLIENT_ID" \
  -d "client_secret=$CLIENT_SECRET" \
  -d "username=user1" \
  -d "password=user1" \
  -d "scope=openid profile email" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")
[[ -n "$USER_TOKEN" ]] || fail "Pas d'access_token pour user1"
echo "$USER_TOKEN" | python3 -c "
import sys, json, base64
t = sys.stdin.read().strip()
p = t.split('.')[1]; p += '=' * (-len(p) % 4)
c = json.loads(base64.urlsafe_b64decode(p))
roles = c.get('realm_access', {}).get('roles', [])
assert 'admin' not in roles, 'user1 ne doit pas avoir le role admin'
assert 'user' in roles, f'user1 doit avoir le role user, roles={roles}'
"
green "Token user1 OK (role user, pas admin)"

# --- 5. Server health ---
info "Test 5: Server FastAPI health"
HEALTH=$(curl -sf "$SERVER_URL/api/health" || echo "")
[[ "$HEALTH" == '{"status":"ok"}' ]] || fail "Server ne répond pas ($HEALTH)"
green "Server healthy"

# --- 6. Server OIDC activé ? ---
info "Test 6: Server OIDC_ENABLED"
OIDC_STATE=$(docker compose exec -T server printenv OIDC_ENABLED 2>/dev/null || echo "false")
echo "  OIDC_ENABLED=$OIDC_STATE"
if [[ "$OIDC_STATE" == "true" ]]; then
  # --- 6a. Server accepte un JWT valide ---
  info "Test 6a: Server accepte un Bearer JWT valide (admin)"
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SERVER_URL/api/agents" \
    -H "Authorization: Bearer $ADMIN_TOKEN" || echo "000")
  [[ "$STATUS" == "200" ]] || fail "Server rejette le JWT valide (HTTP $STATUS)"
  green "Server accepte le JWT admin (HTTP 200)"

  # --- 6b. Server rejette un token invalide ---
  info "Test 6b: Server rejette un Bearer invalide"
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SERVER_URL/api/agents" \
    -H "Authorization: Bearer invalid.token.here" || echo "000")
  [[ "$STATUS" == "401" ]] || fail "Server devrait renvoyer 401 (HTTP $STATUS)"
  green "Server rejette le token invalide (HTTP 401)"

  # --- 6c. Server rejette sans token ---
  info "Test 6c: Server rejette sans Authorization"
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$SERVER_URL/api/agents" || echo "000")
  [[ "$STATUS" == "401" ]] || fail "Server devrait renvoyer 401 sans token (HTTP $STATUS)"
  green "Server rejette sans token (HTTP 401)"
else
  red "OIDC_ENABLED=false — tests JWT server ignorés (activer avec OIDC_ENABLED=true dans .env)"
fi

# --- 7. JWKS du server vers Keycloak ---
info "Test 7: Server peut joindre Keycloak (JWKS)"
JWKS_STATUS=$(docker compose exec -T server python3 -c "
import urllib.request, sys
try:
    r = urllib.request.urlopen('http://keycloak:8080/realms/$REALM/protocol/openid-connect/certs', timeout=5)
    print(r.status)
except Exception as e:
    print('ERR:', e, file=sys.stderr); sys.exit(1)
" 2>&1 || echo "FAIL")
[[ "$JWKS_STATUS" == "200" ]] || fail "Server ne peut pas joindre Keycloak JWKS ($JWKS_STATUS)"
green "Server → Keycloak JWKS OK"

echo ""
green "=========================================="
green "  TOUS LES TESTS SSO ONT RÉUSSI"
green "=========================================="
