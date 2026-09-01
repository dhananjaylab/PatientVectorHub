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
import Keycloak from 'keycloak-js'
import { ROLE_PRIORITY, type Role } from './rbac'

const AUTH_ENABLED = import.meta.env.VITE_AUTH_ENABLED === 'true'

export const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL,
  realm: import.meta.env.VITE_KEYCLOAK_REALM,
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID,
})

let initPromise: Promise<boolean> | null = null
let refreshPromise: Promise<boolean> | null = null

// Bug fix (found while investigating a reported "keeps crashing while
// logging in" issue): keycloak-js's own kc.clearToken() unconditionally
// calls kc.login() again whenever kc.loginRequired is true (set by
// onLoad: 'login-required' above) -- see keycloak-js's dist/keycloak.mjs,
// `clearToken = function() { ... if (kc.loginRequired) { kc.login(); } }`.
// clearToken() is called internally whenever authSuccess()'s own
// validation of a returned callback fails (nonce mismatch is one
// concrete trigger, reproduced directly against a real, unmodified
// keycloak-js v24.0.5 via a full authorization-code+PKCE round trip
// against a controlled OIDC stand-in -- not assumed from reading the
// source alone). With no circuit breaker, ANY recurring cause of that
// validation failing (a misconfigured realm/client, clock skew, a
// browser blocking storage in some contexts, or simply Keycloak being
// briefly unreachable mid-flow) turns into a genuine infinite redirect
// loop: browser bounces to Keycloak, back, fails validation, bounces
// to Keycloak again, forever -- which is exactly what "keeps crashing"
// looks like from the outside, both during and immediately after the
// visible login screen.
//
// Fixed at the application layer (not by patching the vendored
// library, which would need re-applying on every keycloak-js upgrade):
// sessionStorage tracks how many times in a row we've landed back with
// OAuth callback params still in the URL. Exceeding the threshold means
// keycloak-js is not making forward progress -- stop calling
// keycloak.init() again and surface a clear, actionable error instead
// of continuing to silently loop. Resets on any genuinely fresh
// (non-callback) load or a successful init, so it never wrongly blocks
// a later, legitimate login.
const LOGIN_ATTEMPT_KEY = 'pvh-login-attempt-count'
const MAX_LOGIN_ATTEMPTS = 3

function hasOAuthCallbackParams(): boolean {
  // Matches the shape keycloak-js's own parseCallbackUrl() looks for
  // with responseMode='fragment' (this app's default -- see keycloak.init
  // below, which doesn't override responseMode): a 'state' param plus
  // either 'code' (success) or 'error' (Keycloak-side failure) in the
  // URL hash.
  const hash = window.location.hash
  return hash.includes('state=') && (hash.includes('code=') || hash.includes('error='))
}

export class LoginLoopError extends Error {
  constructor(attempts: number) {
    super(
      `Login failed ${attempts} times in a row without completing (repeated redirect loop ` +
        'detected). This means Keycloak is rejecting or losing track of the callback each ' +
        'time (a common cause: nonce/state validation failing on every attempt) rather than ' +
        'a one-off network blip. Check the browser console for "[KEYCLOAK]" messages, and ' +
        'verify infra/keycloak/realm.json\'s pvh-spa client redirectUris/webOrigins exactly ' +
        'match the URL this app is actually being served from.',
    )
    this.name = 'LoginLoopError'
  }
}

function checkLoginLoopGuard(): void {
  if (!hasOAuthCallbackParams()) {
    // A genuinely fresh load (no callback params) -- any earlier
    // failure streak is no longer relevant.
    sessionStorage.removeItem(LOGIN_ATTEMPT_KEY)
    return
  }
  const attempts = Number(sessionStorage.getItem(LOGIN_ATTEMPT_KEY) ?? '0') + 1
  if (attempts > MAX_LOGIN_ATTEMPTS) {
    sessionStorage.removeItem(LOGIN_ATTEMPT_KEY)
    throw new LoginLoopError(attempts - 1)
  }
  sessionStorage.setItem(LOGIN_ATTEMPT_KEY, String(attempts))
}

export interface AuthUser {
  userId: string
  email: string
  role: Role
  tenantId: string
}

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
export async function initKeycloak(): Promise<boolean> {
  if (!AUTH_ENABLED) {
    return false
  }
  if (!initPromise) {
    try {
      checkLoginLoopGuard()
    } catch (err) {
      initPromise = Promise.reject(err)
      return initPromise
    }
    console.log('[KEYCLOAK] Initializing with endpoint:', keycloak.authServerUrl)
    
    initPromise = keycloak
      .init({
        onLoad: 'login-required',
        pkceMethod: 'S256',
        checkLoginIframe: false,
        enableLogging: true,
      })
      .then((authenticated) => {
        console.log('[KEYCLOAK] Authentication result:', authenticated)
        sessionStorage.removeItem(LOGIN_ATTEMPT_KEY)
        return authenticated
      })
      .catch((err) => {
        console.error('[KEYCLOAK] Init failed:', err)
        // Don't reset initPromise — let the error propagate
        // so the app can handle it gracefully in App.tsx
        throw err
      })
  }
  return initPromise
}

export function normalizeClaimString(value: unknown): string {
  if (typeof value === 'string') {
    return value
  }
  if (Array.isArray(value) && value.length === 1 && typeof value[0] === 'string') {
    return value[0]
  }
  return ''
}

export function extractAuthUser(tokenParsed: Record<string, unknown>): AuthUser {
  const realmRoles = (tokenParsed['realm_access'] as { roles?: string[] } | undefined)?.roles ?? []
  const resourceRoles = Object.values((tokenParsed['resource_access'] as Record<string, { roles?: string[] }> | undefined) ?? {}).flatMap((r) => r.roles ?? [])
  const allRoles = [...realmRoles, ...resourceRoles].map((r) => String(r).toLowerCase())
  const role = (ROLE_PRIORITY.find((r) => allRoles.includes(r)) ?? 'readonly') as Role

  return {
    userId: normalizeClaimString(tokenParsed['sub']),
    email: normalizeClaimString(tokenParsed['email']) || normalizeClaimString(tokenParsed['preferred_username']),
    role,
    tenantId: normalizeClaimString(tokenParsed['tenant_id']),
  }
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
export async function getValidToken(): Promise<string | null> {
  if (!AUTH_ENABLED || !keycloak.authenticated) {
    return null
  }
  try {
    refreshPromise ??= keycloak.updateToken(30).finally(() => {
      refreshPromise = null
    })
    await refreshPromise
  } catch {
    // Refresh failed (e.g. refresh token itself expired) — fall through
    // and let the 401 interceptor in lib/api.ts redirect to login rather
    // than silently sending a stale/invalid token.
    return null
  }
  return keycloak.token ?? null
}

export function logout(): void {
  if (AUTH_ENABLED) {
    void keycloak.logout({ redirectUri: window.location.origin })
  }
}

export function login(): void {
  if (AUTH_ENABLED) {
    void keycloak.login({ redirectUri: window.location.origin })
  }
}

export function hasActiveAuthSession(): boolean {
  return AUTH_ENABLED && keycloak.authenticated === true
}

export const isAuthEnabled = AUTH_ENABLED
