import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const keycloakClient = vi.hoisted(() => ({
  init: vi.fn(),
  updateToken: vi.fn(),
  logout: vi.fn(),
  login: vi.fn(),
  authenticated: true,
  token: 'token-1',
  tokenParsed: null,
}))

vi.mock('keycloak-js', () => ({
  default: vi.fn(function KeycloakMock() {
    return keycloakClient
  }),
}))

beforeEach(() => {
  vi.resetModules()
  vi.stubEnv('VITE_AUTH_ENABLED', 'true')
  vi.stubEnv('VITE_KEYCLOAK_URL', 'http://localhost:8080')
  vi.stubEnv('VITE_KEYCLOAK_REALM', 'patientvectorhub')
  vi.stubEnv('VITE_KEYCLOAK_CLIENT_ID', 'pvh-spa')
  keycloakClient.init.mockReset()
  keycloakClient.updateToken.mockReset()
  keycloakClient.logout.mockReset()
  keycloakClient.login.mockReset()
  keycloakClient.authenticated = true
  keycloakClient.token = 'token-1'
})

describe('initKeycloak', () => {
  it('coalesces concurrent init calls into one keycloak-js init', async () => {
    keycloakClient.init.mockResolvedValue(true)
    const { initKeycloak } = await import('../keycloak')

    await expect(Promise.all([initKeycloak(), initKeycloak()])).resolves.toEqual([true, true])
    expect(keycloakClient.init).toHaveBeenCalledTimes(1)
  })

  it('does not reinitialize after the first init resolves', async () => {
    keycloakClient.init.mockResolvedValue(true)
    const { initKeycloak } = await import('../keycloak')

    await initKeycloak()
    await initKeycloak()

    expect(keycloakClient.init).toHaveBeenCalledTimes(1)
  })
})

describe('getValidToken', () => {
  it('coalesces concurrent token refreshes and returns the current token', async () => {
    keycloakClient.updateToken.mockResolvedValue(true)
    const { getValidToken } = await import('../keycloak')

    await expect(Promise.all([getValidToken(), getValidToken()])).resolves.toEqual(['token-1', 'token-1'])
    expect(keycloakClient.updateToken).toHaveBeenCalledTimes(1)
  })
})

describe('extractAuthUser', () => {
  it('normalizes a single-item tenant_id array from Keycloak user attributes', async () => {
    const { extractAuthUser } = await import('../keycloak')

    expect(
      extractAuthUser({
        sub: 'subject-1',
        email: 'admin@tenant1.test',
        tenant_id: ['00000000-0000-0000-0000-000000000001'],
        realm_access: { roles: ['admin'] },
      }),
    ).toEqual({
      userId: 'subject-1',
      email: 'admin@tenant1.test',
      role: 'admin',
      tenantId: '00000000-0000-0000-0000-000000000001',
    })
  })
})

/**
 * Bug fix coverage: keycloak-js's own kc.clearToken() unconditionally
 * calls kc.login() again whenever onLoad: 'login-required' is set (see
 * lib/keycloak.ts's own comment above initKeycloak, and this repo's
 * PHASE_10 follow-up notes for the full reproduction against a real,
 * unmodified keycloak-js). With no circuit breaker, any recurring cause
 * of authSuccess()'s internal validation failing turns into a genuine
 * infinite redirect loop -- reproduced live via a real browser against
 * a controlled OIDC stand-in, not assumed from reading the library
 * source alone.
 *
 * These tests can't reproduce keycloak-js's OWN internal clearToken()
 * call (that lives inside the mocked library here), so they instead
 * verify this module's own contract: the guard trips after
 * MAX_LOGIN_ATTEMPTS renewed sightings of callback params in the URL,
 * does so BEFORE calling keycloak.init() again (not after, since a
 * thrown error can't cancel a navigation the library already started),
 * and does not double-count React StrictMode's double effect
 * invocation.
 */
describe('login loop guard', () => {
  function setCallbackHash(state = 'state-abc', code = 'code-xyz') {
    window.location.hash = `#state=${state}&session_state=sess-1&code=${code}`
  }

  function setFreshHash() {
    window.location.hash = ''
  }

  afterEach(() => {
    sessionStorage.clear()
    window.location.hash = ''
  })

  it('does not throw and calls keycloak.init() on a fresh (non-callback) load', async () => {
    setFreshHash()
    keycloakClient.init.mockResolvedValue(true)
    const { initKeycloak } = await import('../keycloak')

    await expect(initKeycloak()).resolves.toBe(true)
    expect(keycloakClient.init).toHaveBeenCalledTimes(1)
  })

  it('does not throw while under the attempt threshold', async () => {
    setCallbackHash()
    keycloakClient.init.mockResolvedValue(true)
    const { initKeycloak } = await import('../keycloak')

    await expect(initKeycloak()).resolves.toBe(true)
    expect(keycloakClient.init).toHaveBeenCalledTimes(1)
  })

  it('throws LoginLoopError once the threshold is exceeded, WITHOUT calling keycloak.init() again', async () => {
    setCallbackHash()
    // Pre-seed the counter as if 3 prior page loads already landed here
    // with callback params still present and failing to progress --
    // matches what checkLoginLoopGuard itself writes, so this doesn't
    // assume a private implementation detail beyond the documented key.
    sessionStorage.setItem('pvh-login-attempt-count', '3')
    const { initKeycloak, LoginLoopError } = await import('../keycloak')

    await expect(initKeycloak()).rejects.toThrow(LoginLoopError)
    // The critical assertion: keycloak.init() must NEVER be called on
    // the attempt that trips the breaker -- that's the entire point.
    // Calling it and THEN throwing would be too late, since
    // keycloak-js's own internal clearToken()->login() (not reachable
    // from this mock) fires as a side effect of that call, before any
    // exception from a later step could matter.
    expect(keycloakClient.init).not.toHaveBeenCalled()
  })

  it('resets the counter on a genuinely fresh load after a prior failure streak', async () => {
    sessionStorage.setItem('pvh-login-attempt-count', '3')
    setFreshHash()
    keycloakClient.init.mockResolvedValue(true)
    const { initKeycloak } = await import('../keycloak')

    await expect(initKeycloak()).resolves.toBe(true)
    expect(sessionStorage.getItem('pvh-login-attempt-count')).toBeNull()
  })

  it('clears the counter after a successful init', async () => {
    setCallbackHash()
    sessionStorage.setItem('pvh-login-attempt-count', '1')
    keycloakClient.init.mockResolvedValue(true)
    const { initKeycloak } = await import('../keycloak')

    await initKeycloak()
    expect(sessionStorage.getItem('pvh-login-attempt-count')).toBeNull()
  })

  it('does not double-count React StrictMode-style concurrent invocations on the same page load', async () => {
    // Regression test for the actual bug found while verifying the fix:
    // the guard was originally checked on every initKeycloak() call,
    // but StrictMode invokes the effect (and therefore this function)
    // twice per real page load. Checking on every call meant the
    // counter advanced by 2 per real cycle, and -- more importantly --
    // the FIRST of the two calls had already reached keycloak.init()
    // before the SECOND call's throw could matter. Gating the guard
    // behind the same `!initPromise` singleton that already coalesces
    // concurrent init calls (see the 'coalesces concurrent init calls'
    // test above) fixes both: the guard now runs at most once per real
    // page load, synchronized with how often keycloak.init() actually
    // gets called.
    setCallbackHash()
    sessionStorage.setItem('pvh-login-attempt-count', '3')
    keycloakClient.init.mockResolvedValue(true)
    const { initKeycloak, LoginLoopError } = await import('../keycloak')

    // Two "concurrent" calls, matching how React StrictMode fires an
    // effect's body twice in the same synchronous window.
    const results = await Promise.allSettled([initKeycloak(), initKeycloak()])

    expect(results[0].status).toBe('rejected')
    expect(results[1].status).toBe('rejected')
    if (results[0].status === 'rejected') {
      expect(results[0].reason).toBeInstanceOf(LoginLoopError)
    }
    // Both calls must see the SAME outcome (the second one reuses the
    // first's already-rejected initPromise rather than re-running the
    // guard against a reset counter) -- and neither ever reaches
    // keycloak.init().
    expect(keycloakClient.init).not.toHaveBeenCalled()
  })

  it('LoginLoopError message names the likely real-world causes', async () => {
    setCallbackHash()
    sessionStorage.setItem('pvh-login-attempt-count', '3')
    const { initKeycloak } = await import('../keycloak')

    await expect(initKeycloak()).rejects.toThrow(/redirect loop/i)
  })
})
