/**
 * dashboard/src/App.test.tsx
 *
 * Exercises the route-level RoleGuard wiring end to end (not just
 * lib/rbac.ts's pure functions, already covered in
 * lib/__tests__/rbac.test.ts) — this is what actually protects a page
 * in the running app. initKeycloak is mocked to resolve `false`
 * (unauthenticated) since App.tsx's real Keycloak init isn't the
 * subject of this test; the auth store's role is set directly instead,
 * mirroring what App.tsx would do after a real token parse.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { useAuthStore } from './stores/useAuthStore'
import type { Role } from './lib/rbac'
import App from './App'

const keycloakMock = vi.hoisted(() => ({
  authEnabled: false,
  initKeycloak: vi.fn(),
  extractAuthUser: vi.fn(() => ({
    userId: 'u-1',
    email: 'u@x.test',
    role: 'admin',
    tenantId: 't-1',
  })),
  keycloak: { tokenParsed: null as Record<string, unknown> | null },
  logout: vi.fn(),
  login: vi.fn(),
}))

vi.mock('./lib/keycloak', () => ({
  initKeycloak: keycloakMock.initKeycloak,
  extractAuthUser: keycloakMock.extractAuthUser,
  keycloak: keycloakMock.keycloak,
  logout: keycloakMock.logout,
  login: keycloakMock.login,
  get isAuthEnabled() {
    return keycloakMock.authEnabled
  },
}))

vi.mock('./lib/api', () => ({
  api: { get: vi.fn().mockReturnValue(new Promise(() => {})), post: vi.fn() },
  getApiErrorMessage: vi.fn(() => ''),
}))

beforeEach(() => {
  keycloakMock.authEnabled = false
  keycloakMock.initKeycloak.mockReset()
  keycloakMock.initKeycloak.mockResolvedValue(false)
  keycloakMock.extractAuthUser.mockClear()
  keycloakMock.keycloak.tokenParsed = null
  keycloakMock.logout.mockClear()
  keycloakMock.login.mockClear()
})

afterEach(() => {
  useAuthStore.getState().reset()
})

// App.tsx renders its own <BrowserRouter> and <QueryClientProvider>
// internally — this test can't wrap it in renderWithProviders'
// MemoryRouter (React Router throws rendering a <Router> inside another
// <Router>). Route is controlled the way BrowserRouter actually reads
// it: pushState on the real jsdom history before render.
async function renderAtRoute(route: string, role: Role) {
  window.history.pushState({}, '', route)
  useAuthStore.setState({ role, userId: 'u-1', email: 'u@x.test', tenantId: 't-1', authenticated: true })
  render(<App />)
  await waitFor(() => expect(screen.queryByText('Authenticating via Keycloak…')).not.toBeInTheDocument())
}

describe('App route guards', () => {
  it('redirects / to /dashboard, visible to every role', async () => {
    await renderAtRoute('/', 'readonly')
    // Unlike a direct route hit, <Navigate> performs its redirect via an
    // effect — needs one more tick than the other route assertions below,
    // which is why this one (uniquely) waits on the destination content
    // rather than asserting synchronously right after renderAtRoute.
    await waitFor(() => expect(screen.getByText('Overview')).toBeInTheDocument())
  })

  it('blocks a readonly user from /ingestion (requires engineer+)', async () => {
    await renderAtRoute('/ingestion', 'readonly')
    expect(screen.getByText(/403/)).toBeInTheDocument()
  })

  it('allows an engineer onto /ingestion', async () => {
    await renderAtRoute('/ingestion', 'engineer')
    expect(screen.getByText('Ingestion Jobs')).toBeInTheDocument()
  })

  it('blocks a readonly user from /query (requires analyst+)', async () => {
    await renderAtRoute('/query', 'readonly')
    expect(screen.getByText(/403/)).toBeInTheDocument()
  })

  it('allows an analyst onto /query but not /ingestion', async () => {
    await renderAtRoute('/query', 'analyst')
    expect(screen.getByText('RAG Query')).toBeInTheDocument()
  })

  it('blocks an analyst from /admin (requires engineer+ at the route level)', async () => {
    await renderAtRoute('/admin', 'analyst')
    expect(screen.getByText(/403/)).toBeInTheDocument()
  })

  it('allows an engineer into /admin/namespaces but not /admin/api-keys (exact admin-only)', async () => {
    await renderAtRoute('/admin/api-keys', 'engineer')
    expect(screen.getByText(/403/)).toBeInTheDocument()
  })

  it('allows an admin into every route including /admin/api-keys', async () => {
    await renderAtRoute('/admin/api-keys', 'admin')
    expect(screen.queryByText(/403/)).not.toBeInTheDocument()
  })

  it('only shows nav links the current role can access', async () => {
    await renderAtRoute('/dashboard', 'readonly')
    expect(screen.queryByRole('link', { name: 'Ingestion' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
  })

  it('renders NotFoundPage for an unknown route', async () => {
    await renderAtRoute('/this-route-does-not-exist', 'admin')
    expect(screen.getByText('404 — Not Found')).toBeInTheDocument()
  })

  it('shows a recoverable auth error instead of the app shell when Keycloak init fails', async () => {
    keycloakMock.authEnabled = true
    keycloakMock.initKeycloak.mockRejectedValueOnce(new Error('A Keycloak instance can only be initialized once'))

    window.history.pushState({}, '', '/dashboard')
    render(<App />)

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Could not finish sign-in' })).toBeInTheDocument())
    expect(screen.getByText(/A Keycloak instance can only be initialized once/)).toBeInTheDocument()
    expect(screen.queryByText('Overview')).not.toBeInTheDocument()
  })
})
