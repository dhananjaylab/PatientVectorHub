/**
 * dashboard/src/pages/DashboardPage.tsx
 *
 * New in Phase 9. Deliberately light — a real "ingestion health summary,
 * vector store stats, recent queries, active alerts" landing page (doc
 * 03's description) needs metrics endpoints that don't exist yet
 * (Prometheus/Grafana is Phase 10, Observability & Security — see
 * MonitoringPage.tsx's docstring for the same boundary). What IS wired
 * here — namespace health and job counts — uses endpoints that already
 * exist and are real, live data, not placeholders.
 */
import { Link } from 'react-router'
import { useAuthStore } from '../stores/useAuthStore'
import { hasMinRole } from '../lib/rbac'
import { useIngestionJobs } from '../hooks/useIngestionJobs'
import { useNamespaceHealth } from '../hooks/useAdmin'
import { StatusBadge } from '../components/common/StatusBadge'

export function DashboardPage() {
  const { role } = useAuthStore()
  const canSeeIngestion = hasMinRole(role, 'engineer')
  const { data: jobsPage } = useIngestionJobs({ limit: 5 })
  const { data: health } = useNamespaceHealth()

  const running = jobsPage?.jobs.filter((j) => j.status === 'running' || j.status === 'queued') ?? []

  return (
    <div className="dashboard-page">
      <h1>Overview</h1>

      <div className="summary-grid">
        {canSeeIngestion && (
          <div className="summary-card">
            <span className="summary-card-label">Active ingestion jobs</span>
            <span className="summary-card-value">{running.length}</span>
            <Link to="/ingestion" className="summary-card-link">
              View all →
            </Link>
          </div>
        )}

        {canSeeIngestion && (
          <div className="summary-card">
            <span className="summary-card-label">Vector store</span>
            {health ? (
              <>
                <span className="summary-card-value">
                  <StatusBadge status={health.healthy ? 'active' : 'failed'} label={health.healthy ? 'healthy' : 'unreachable'} />
                </span>
                <span className="summary-card-sub mono">{health.backend}</span>
              </>
            ) : (
              <span className="summary-card-value">—</span>
            )}
          </div>
        )}

        {hasMinRole(role, 'analyst') && (
          <div className="summary-card">
            <span className="summary-card-label">RAG query</span>
            <Link to="/query" className="btn-primary summary-card-cta">
              Run a query →
            </Link>
          </div>
        )}
      </div>

      {canSeeIngestion && running.length > 0 && (
        <div className="recent-jobs">
          <h2>Recent activity</h2>
          <ul>
            {running.map((j) => (
              <li key={j.jobId}>
                <span>{j.name}</span>
                <StatusBadge status={j.status} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
