/**
 * PatientVectorHub — Root App
 * Phase 1: Keycloak init + route skeleton.
 * Routes become active as phases complete.
 */
import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { initKeycloak, keycloak } from './lib/keycloak'
import { useAuthStore } from './stores/useAuthStore'

const qc = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
})

const ROLE_LEVEL: Record<string, number> = {
  admin: 4, engineer: 3, analyst: 2, auditor: 1, readonly: 0,
}

interface GuardProps { children: JSX.Element; min: string }
function Guard({ children, min }: GuardProps) {
  const { role } = useAuthStore()
  if ((ROLE_LEVEL[role] ?? -1) < (ROLE_LEVEL[min] ?? 0)) {
    return <div className="error-403">403 — Role '{role}' cannot access this page.</div>
  }
  return children
}

export default function App() {
  const [ready, setReady] = useState(false)
  const { setUser } = useAuthStore()

  useEffect(() => {
    initKeycloak()
      .then(authed => {
        if (authed && keycloak.tokenParsed) {
          const t = keycloak.tokenParsed as Record<string, unknown>
          const roles = (t['realm_access'] as { roles?: string[] })?.roles ?? []
          const priority = ['admin', 'engineer', 'analyst', 'auditor', 'readonly']
          const role = priority.find(r => roles.includes(r)) ?? 'readonly'
          setUser({
            userId:   String(t['sub'] ?? ''),
            email:    String(t['email'] ?? ''),
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
        <Routes>
          <Route path="/"              element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard"     element={<DashboardPlaceholder />} />
          <Route path="/ingestion"     element={<Guard min="engineer"><PlaceholderPage title="Ingestion" /></Guard>} />
          <Route path="/ingestion/new" element={<Guard min="engineer"><PlaceholderPage title="New Ingest Job" /></Guard>} />
          <Route path="/query"         element={<Guard min="analyst"><PlaceholderPage title="RAG Query" /></Guard>} />
          <Route path="/audit-logs"    element={<Guard min="auditor"><PlaceholderPage title="Audit Logs" /></Guard>} />
          <Route path="/monitoring"    element={<Guard min="engineer"><PlaceholderPage title="Monitoring" /></Guard>} />
          <Route path="/admin/*"       element={<Guard min="admin"><PlaceholderPage title="Admin" /></Guard>} />
          <Route path="*"              element={<PlaceholderPage title="404 — Not Found" />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

function DashboardPlaceholder() {
  const { email, role, tenantId } = useAuthStore()
  return (
    <div style={{ padding: '2rem', color: '#E2E8F0' }}>
      <h1 style={{ color: '#00B4D8', marginBottom: '1rem' }}>
        PatientVectorHub Dashboard
      </h1>
      <p><strong>User:</strong> {email || 'Loading…'}</p>
      <p><strong>Role:</strong> {role}</p>
      <p><strong>Tenant:</strong> {tenantId}</p>
      <p style={{ marginTop: '1rem', color: '#94A3B8' }}>
        Phase 1 complete — feature pages load in subsequent phases.
      </p>
    </div>
  )
}

function PlaceholderPage({ title }: { title: string }) {
  return (
    <div style={{ padding: '2rem', color: '#94A3B8' }}>
      <h2 style={{ color: '#E2E8F0' }}>{title}</h2>
      <p>Coming in later phases.</p>
    </div>
  )
}
