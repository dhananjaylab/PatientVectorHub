/**
 * PatientVectorHub — Root App
 *
 * Phase 9: real routes replace every PlaceholderPage from Phase 1.
 * Import source changed from 'react-router-dom' to 'react-router' —
 * react-router v8 removed the `-dom` package entirely; declarative
 * components (BrowserRouter/Routes/Route/Navigate/Link/NavLink) and
 * hooks all live in the base `react-router` package now. Verified
 * directly against the installed v8.3.0 package rather than assumed
 * from the migration notes, which describe `react-router/dom` as the
 * home for "DOM-specific APIs" — in practice that subpath only exports
 * RouterProvider/HydratedRouter (the data-router / framework-mode API
 * this app doesn't use); BrowserRouter itself ships from the main
 * entry point, same import site as everything else here.
 */
import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { extractAuthUser, initKeycloak, isAuthEnabled, keycloak, login } from './lib/keycloak'
import { ErrorBoundary } from './components/common/ErrorBoundary'
import { useAuthStore } from './stores/useAuthStore'
import { RoleGuard } from './components/common/RoleGuard'
import { AppLayout } from './components/layout/AppLayout'
import { DashboardPage } from './pages/DashboardPage'
import { IngestionPage } from './pages/IngestionPage'
import { NewJobPage } from './pages/NewJobPage'
import { QueryPage } from './pages/QueryPage'
import { AuditLogPage } from './pages/AuditLogPage'
import { MonitoringPage } from './pages/MonitoringPage'
import { AdminLayout } from './pages/admin/AdminLayout'
import { AdminApiKeysPage } from './pages/admin/AdminApiKeysPage'
import { AdminUsersPage } from './pages/admin/AdminUsersPage'
import { AdminNamespacesPage } from './pages/admin/AdminNamespacesPage'
import { NotFoundPage } from './pages/NotFoundPage'

const qc = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
})

export default function App() {
  const [ready, setReady] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)
  const { setUser } = useAuthStore()

  useEffect(() => {
    initKeycloak()
      .then((authed) => {
        if (authed && keycloak.tokenParsed) {
          setUser(extractAuthUser(keycloak.tokenParsed as Record<string, unknown>))
        } else if (!isAuthEnabled && !useAuthStore.getState().authenticated) {
          setUser({
            userId: 'local-dev-user',
            email: 'dev@localhost',
            role: 'admin',
            tenantId: 'default',
          })
        }
        setReady(true)
      })
      .catch((err: unknown) => {
        if (!isAuthEnabled && !useAuthStore.getState().authenticated) {
          setUser({
            userId: 'local-dev-user',
            email: 'dev@localhost',
            role: 'admin',
            tenantId: 'default',
          })
          setReady(true)
          return
        }
        const message = err instanceof Error ? err.message : 'Could not complete Keycloak authentication.'
        setAuthError(message)
        setReady(true)
      })
  }, [setUser])

  if (!ready) {
    return <div className="auth-loading">Authenticating via Keycloak…</div>
  }

  if (authError) {
    return (
      <div className="auth-error-page">
        <div className="auth-error-panel">
          <p className="eyebrow">Authentication interrupted</p>
          <h1>Could not finish sign-in</h1>
          <p className="auth-error-copy">
            Keycloak is expected at <span className="mono">http://localhost:8080</span>. Check that the local realm is running, then try again.
          </p>
          <pre className="auth-error-detail">{authError}</pre>
          <div className="auth-error-actions">
            <button
              type="button"
              className="btn-primary"
              onClick={() => {
                // Bug fix: this used to check window.location.search, but
                // keycloak.init() below never overrides responseMode, so
                // it defaults to 'fragment' -- state/code/error land in
                // window.location.hash, not the query string. The old
                // check silently never matched anything, leaving a stale
                // (already-consumed, now-invalid) callback hash in place
                // across a reload.
                if (window.location.hash.includes('state=')) {
                  window.history.replaceState({}, '', window.location.pathname)
                }
                window.location.reload()
              }}
            >
              Retry
            </button>
            <button type="button" className="btn-ghost" onClick={login}>
              Sign in again
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <ErrorBoundary>
      <QueryClientProvider client={qc}>
        <BrowserRouter>
          <AppLayout>
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />

              <Route path="/ingestion" element={<RoleGuard min="engineer"><IngestionPage /></RoleGuard>} />
              <Route path="/ingestion/new" element={<RoleGuard min="engineer"><NewJobPage /></RoleGuard>} />

              <Route path="/query" element={<RoleGuard min="analyst"><QueryPage /></RoleGuard>} />

              <Route path="/audit-logs" element={<RoleGuard min="auditor"><AuditLogPage /></RoleGuard>} />

              <Route path="/monitoring" element={<RoleGuard min="engineer"><MonitoringPage /></RoleGuard>} />

              <Route
                path="/admin"
                element={
                  <RoleGuard min="engineer">
                    <AdminLayout />
                  </RoleGuard>
                }
              >
                <Route index element={<Navigate to="/admin/api-keys" replace />} />
                <Route path="api-keys" element={<AdminApiKeysPage />} />
                <Route path="users" element={<AdminUsersPage />} />
                <Route path="namespaces" element={<AdminNamespacesPage />} />
              </Route>

              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </AppLayout>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
