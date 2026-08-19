/**
 * dashboard/src/components/layout/AppLayout.tsx
 *
 * New in Phase 9. Sidebar nav items are filtered by hasMinRole() against
 * doc 03's per-route access column, so a person only ever sees links to
 * pages they can actually open — matches this codebase's general
 * "filter, don't error" precedent elsewhere (routers/audit.py's
 * self-scoping instead of a 403 on a mismatched filter) applied to
 * navigation instead of data.
 */
import type { ReactNode } from 'react'
import { Link, NavLink } from 'react-router'
import { useAuthStore } from '../../stores/useAuthStore'
import { hasMinRole, roleLabel, type Role } from '../../lib/rbac'
import { logout, isAuthEnabled } from '../../lib/keycloak'

interface NavItem {
  to: string
  label: string
  min: Role
}

const NAV_ITEMS: NavItem[] = [
  { to: '/dashboard', label: 'Dashboard', min: 'readonly' },
  { to: '/ingestion', label: 'Ingestion', min: 'engineer' },
  { to: '/query', label: 'Query', min: 'analyst' },
  { to: '/audit-logs', label: 'Audit Logs', min: 'auditor' },
  { to: '/monitoring', label: 'Monitoring', min: 'engineer' },
  { to: '/admin', label: 'Admin', min: 'admin' },
]

export function AppLayout({ children }: { children: ReactNode }) {
  const { email, role, tenantId } = useAuthStore()

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <Link to="/dashboard" className="app-brand">
          PatientVectorHub
        </Link>
        <nav className="app-nav">
          {NAV_ITEMS.filter((item) => hasMinRole(role, item.min)).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? 'app-nav-link active' : 'app-nav-link')}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="app-main">
        <header className="app-topbar">
          <span className="app-tenant mono">{tenantId ? `tenant: ${tenantId.slice(0, 8)}…` : ''}</span>
          <span className="app-user">
            {email || (isAuthEnabled ? 'Loading…' : 'local-dev (auth disabled)')}
            <span className="role-pill">{roleLabel(role)}</span>
          </span>
          {isAuthEnabled && (
            <button type="button" className="btn-ghost" onClick={logout}>
              Log out
            </button>
          )}
        </header>
        <main className="app-content">{children}</main>
      </div>
    </div>
  )
}
