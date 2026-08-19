/**
 * dashboard/src/lib/keycloak.ts
 *
 * Phase 9. App.tsx has imported `{ initKeycloak, keycloak }` from this
 * exact path since Phase 1 — this file never existed, so that import
 * has been broken since the scaffold was first committed. Every
 * dashboard build/dev-server run before this phase would have failed at
 * module resolution before ever reaching a browser.
 *
 * Config mirrors infra/keycloak/realm.json's `pvh-spa` client exactly:
 * public client, PKCE S256, standardFlowEnabled (authorization-code
 * flow), no client secret (SPA clients don't get one). Matches
 * api-gateway/src/config.py's KEYCLOAK_BASE_URL / KEYCLOAK_REALM /
 * KEYCLOAK_CLIENT_ID defaults via the VITE_KEYCLOAK_* env vars — see
 * .env.example for why these need their own VITE_-prefixed copies
 * rather than reading the backend's .env directly.
 *
 * `onLoad: 'login-required'` (not 'check-sso'): this is an internal
 * operational dashboard, not a page with a legitimate anonymous-browsing
 * mode, so forcing an immediate redirect to Keycloak's login page for an
 * unauthenticated visitor is the correct default — matches the intent
 * doc 40's original App.tsx sketch already encoded. 'check-sso' (silent
 * iframe check, no forced redirect) would need a static
 * silent-check-sso.html page under dashboard/public/ that doesn't exist
 * and isn't needed for this flow.
 */
import Keycloak from 'keycloak-js';

// In Node.js environments (e.g. Playwright tests), import.meta.env is undefined.
// Default to safe values that disable auth and prevent Keycloak init.
const getEnv = (key, defaultValue = '') => {
    return import.meta?.env?.[key] ?? defaultValue;
};

const AUTH_ENABLED = getEnv('VITE_AUTH_ENABLED', 'false') === 'true';

// Lazy-initialize Keycloak only when accessed, avoiding 'document is not defined'
// errors in Node.js test environments.
let keycloakInstance = null;
export function getKeycloak() {
    if (!keycloakInstance) {
        keycloakInstance = new Keycloak({
            url: getEnv('VITE_KEYCLOAK_URL', 'http://localhost:8443'),
            realm: getEnv('VITE_KEYCLOAK_REALM', 'patientvectorhub'),
            clientId: getEnv('VITE_KEYCLOAK_CLIENT_ID', 'pvh-spa'),
        });
    }
    return keycloakInstance;
}

// For backward compatibility, provide keycloak as a property getter
export const keycloak = new Proxy({}, {
    get(target, prop) {
        return getKeycloak()[prop];
    }
});
/**
 * Initializes Keycloak and returns whether the session is authenticated.
 *
 * When VITE_AUTH_ENABLED=false (local-dev default, mirrors the backend's
 * AUTH_ENABLED=false), this resolves `false` immediately without ever
 * touching the network — there may be no Keycloak container running at
 * all in that mode, and the backend isn't enforcing auth either, so
 * attempting real PKCE init here would just be a guaranteed failure for
 * no benefit. App.tsx's existing `.catch(() => setReady(true))` around
 * the caller already degrades gracefully if this ever does throw
 * (e.g. Keycloak briefly unreachable in a real deployment).
 */
export async function initKeycloak() {
    if (!AUTH_ENABLED) {
        return false;
    }
    return getKeycloak().init({
        onLoad: 'login-required',
        pkceMethod: 'S256',
        checkLoginIframe: false,
    });
}
/**
 * Returns a token guaranteed valid for at least 30 more seconds,
 * refreshing first if needed. Called by lib/api.ts's request
 * interceptor on every outgoing call — matches doc 10 Flow 1's
 * `keycloak.updateToken(30)` design and api-gateway's 300s JWKS cache
 * window (PyJWKClient in middleware/auth.py) comfortably.
 *
 * Returns null when auth is disabled or there's no active session —
 * callers (lib/api.ts) treat that as "send the request unauthenticated"
 * rather than blocking, matching the backend's own AUTH_ENABLED=false
 * behavior of not requiring a credential at all.
 */
export async function getValidToken() {
    if (!AUTH_ENABLED || !getKeycloak().authenticated) {
        return null;
    }
    try {
        await getKeycloak().updateToken(30);
    }
    catch {
        // Refresh failed (e.g. refresh token itself expired) — fall through
        // and let the 401 interceptor in lib/api.ts redirect to login rather
        // than silently sending a stale/invalid token.
    }
    return getKeycloak().token ?? null;
}
export function logout() {
    if (AUTH_ENABLED) {
        void getKeycloak().logout({ redirectUri: window.location.origin });
    }
}
export const isAuthEnabled = AUTH_ENABLED;
