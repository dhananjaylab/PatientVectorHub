/**
 * dashboard/src/pages/MonitoringPage.tsx
 *
 * Phase 10 / ADR-017. Was a deliberate placeholder in Phase 9 (see git
 * history / ADR-016) — Prometheus/Grafana didn't exist yet. Now that
 * docker-compose.yml runs Grafana with GF_SECURITY_ALLOW_EMBEDDING=true
 * and infra/grafana/dashboards/pvh-overview.json provisions the panels
 * below, this embeds them via Grafana's own "d-solo" single-panel embed
 * URL rather than building a native chart component per metric —
 * matches the original Phase 9 design doc's own language ("Grafana
 * embeds"), and avoids re-implementing PromQL querying + charting in
 * this app when Grafana already does it.
 *
 * The RBAC floor (engineer+) and route were wired in Phase 9 and are
 * unchanged here — only this component's body changed.
 */
import { useState } from 'react'

const GRAFANA_URL = import.meta.env.VITE_GRAFANA_URL
const DASHBOARD_UID = 'pvh-overview'
const DASHBOARD_SLUG = 'patientvectorhub-overview'

interface PanelDef {
  id: number
  title: string
}

// Subset of infra/grafana/dashboards/pvh-overview.json's 9 panels —
// the four the original design doc named by name (ingestion throughput,
// query latency percentiles, Kafka consumer lag, Weaviate index health)
// plus the HTTP error rate panel, since this page's RBAC floor
// (engineer+) is exactly the audience that cares about API health too.
// Panel ids below must stay in sync with that JSON file's own "id"
// fields — there is no dynamic lookup here, deliberately: a mismatch
// fails loudly (wrong/blank panel) rather than silently rendering
// nothing, and pvh-overview.json is this phase's own file, not
// something expected to drift independently.
const PANELS: PanelDef[] = [
  { id: 1, title: 'Ingestion throughput' },
  { id: 2, title: 'Query latency percentiles' },
  { id: 3, title: 'Kafka consumer lag' },
  { id: 4, title: 'HTTP 5xx error rate' },
  { id: 9, title: 'Weaviate index health' },
]

function panelEmbedUrl(panelId: number, refreshToken: number): string {
  const params = new URLSearchParams({
    orgId: '1',
    panelId: String(panelId),
    theme: 'dark',
    from: 'now-6h',
    to: 'now',
    refresh: '30s',
    // Cache-busts the iframe on manual refresh (see handleRefresh below)
    // — Grafana's own auto-refresh=30s already covers the steady-state
    // case; this is only for "I just want it now" without waiting.
    _t: String(refreshToken),
  })
  return `${GRAFANA_URL}/d-solo/${DASHBOARD_UID}/${DASHBOARD_SLUG}?${params.toString()}`
}

export function MonitoringPage() {
  const [refreshToken, setRefreshToken] = useState(0)

  if (!GRAFANA_URL) {
    return (
      <div className="monitoring-page">
        <h1>Monitoring</h1>
        <div className="monitoring-unavailable">
          <p>
            <code className="mono">VITE_GRAFANA_URL</code> is not set — see{' '}
            <code className="mono">dashboard/.env.example</code>. Metrics dashboards require Grafana
            to be running (<code className="mono">docker-compose up grafana prometheus</code>).
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="monitoring-page">
      <h1>Monitoring</h1>
      <div className="monitoring-links">
        <a href={`${GRAFANA_URL}/d/${DASHBOARD_UID}/${DASHBOARD_SLUG}`} target="_blank" rel="noreferrer">
          Open full dashboard in Grafana ↗
        </a>
        <a href={GRAFANA_URL.replace(/:\d+$/, ':16686')} target="_blank" rel="noreferrer">
          Open Jaeger traces ↗
        </a>
        <button type="button" className="btn-ghost" onClick={() => setRefreshToken((t) => t + 1)}>
          Refresh now
        </button>
      </div>
      <div className="monitoring-grid">
        {PANELS.map((panel) => (
          <div className="monitoring-panel" key={panel.id}>
            <div className="monitoring-panel-title">{panel.title}</div>
            <iframe
              src={panelEmbedUrl(panel.id, refreshToken)}
              title={panel.title}
              loading="lazy"
            />
          </div>
        ))}
      </div>
    </div>
  )
}
