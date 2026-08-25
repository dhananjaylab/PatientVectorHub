import { beforeEach, describe, expect, it, vi } from 'vitest'

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
