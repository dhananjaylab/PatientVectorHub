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
import { initKeycloak, keycloak } from './lib/keycloak'
import { useAuthStore } from './stores/useAuthStore'
import { ROLE_PRIORITY, type Role } from './lib/rbac'
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
  const { setUser } = useAuthStore()

  useEffect(() => {
    initKeycloak()
      .then((authed) => {
        if (authed && keycloak.tokenParsed) {
          const t = keycloak.tokenParsed as Record<string, unknown>
          const roles = (t['realm_access'] as { roles?: string[] })?.roles ?? []
          const role = (ROLE_PRIORITY.find((r) => roles.includes(r)) ?? 'readonly') as Role
          setUser({
            userId: String(t['sub'] ?? ''),
            email: String(t['email'] ?? ''),
            role,
            tenantId: String(t['tenant_id'] ?? ''),
          })
        }
        setReady(true)
      })
      .catch(() => setReady(true))
  }, [setUser])

  if (!ready) {
    return <div className="auth-loading">Authenticating via Keycloak…</div>
  }

  return (
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
  )
}
