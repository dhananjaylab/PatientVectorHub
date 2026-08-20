/**
 * dashboard/src/pages/admin/AdminNamespacesPage.tsx
 *
 * New in Phase 9. RoleGuard here is `min="engineer"` — deliberately
 * looser than AdminApiKeysPage / AdminUsersPage's exact admin-only gate,
 * matching GET /v1/admin/vector-store/namespaces's real
 * require_min_role("engineer") on the backend (routers/admin.py's
 * module docstring: "engineers doing ingestion ops need to check
 * vector-store health as routine work").
 */
import { RoleGuard } from '../../components/common/RoleGuard'
import { StatusBadge } from '../../components/common/StatusBadge'
import { useNamespaceHealth } from '../../hooks/useAdmin'
import { getApiErrorMessage } from '../../lib/api'

function NamespaceHealthPanel() {
  const { data, isLoading, isError, error, dataUpdatedAt } = useNamespaceHealth()

  if (isLoading) return <p className="loading-text">Checking vector store health…</p>
  if (isError) return <p className="field-error">{getApiErrorMessage(error)}</p>
  if (!data) return null

  return (
    <div className="namespace-health-panel">
      <div className="summary-card">
        <span className="summary-card-label">Backend</span>
        <span className="summary-card-value mono">{data.backend}</span>
      </div>
      <div className="summary-card">
        <span className="summary-card-label">Status</span>
        <span className="summary-card-value">
          <StatusBadge status={data.healthy ? 'active' : 'failed'} label={data.healthy ? 'healthy' : 'unreachable'} />
        </span>
      </div>
      <div className="summary-card">
        <span className="summary-card-label">Tenant</span>
        <span className="summary-card-value mono">{data.tenant_id.slice(0, 8)}…</span>
      </div>
      <p className="placeholder-sub">Auto-refreshes every 15s. Last checked {new Date(dataUpdatedAt).toLocaleTimeString()}.</p>
    </div>
  )
}

export function AdminNamespacesPage() {
  return (
    <RoleGuard min="engineer">
      <NamespaceHealthPanel />
    </RoleGuard>
  )
}
