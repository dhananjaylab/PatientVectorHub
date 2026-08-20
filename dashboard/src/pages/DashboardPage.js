import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
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
import { Link } from 'react-router';
import { useAuthStore } from '../stores/useAuthStore';
import { hasMinRole } from '../lib/rbac';
import { useIngestionJobs } from '../hooks/useIngestionJobs';
import { useNamespaceHealth } from '../hooks/useAdmin';
import { StatusBadge } from '../components/common/StatusBadge';
export function DashboardPage() {
    const { role } = useAuthStore();
    const canSeeIngestion = hasMinRole(role, 'engineer');
    const { data: jobsPage } = useIngestionJobs({ limit: 5, enabled: canSeeIngestion });
    const { data: health } = useNamespaceHealth(canSeeIngestion);
    const running = jobsPage?.jobs.filter((j) => j.status === 'running' || j.status === 'queued') ?? [];
    return (_jsxs("div", { className: "dashboard-page", children: [_jsx("h1", { children: "Overview" }), _jsxs("div", { className: "summary-grid", children: [canSeeIngestion && (_jsxs("div", { className: "summary-card", children: [_jsx("span", { className: "summary-card-label", children: "Active ingestion jobs" }), _jsx("span", { className: "summary-card-value", children: running.length }), _jsx(Link, { to: "/ingestion", className: "summary-card-link", children: "View all \u2192" })] })), canSeeIngestion && (_jsxs("div", { className: "summary-card", children: [_jsx("span", { className: "summary-card-label", children: "Vector store" }), health ? (_jsxs(_Fragment, { children: [_jsx("span", { className: "summary-card-value", children: _jsx(StatusBadge, { status: health.healthy ? 'active' : 'failed', label: health.healthy ? 'healthy' : 'unreachable' }) }), _jsx("span", { className: "summary-card-sub mono", children: health.backend })] })) : (_jsx("span", { className: "summary-card-value", children: "\u2014" }))] })), hasMinRole(role, 'analyst') && (_jsxs("div", { className: "summary-card", children: [_jsx("span", { className: "summary-card-label", children: "RAG query" }), _jsx(Link, { to: "/query", className: "btn-primary summary-card-cta", children: "Run a query \u2192" })] }))] }), canSeeIngestion && running.length > 0 && (_jsxs("div", { className: "recent-jobs", children: [_jsx("h2", { children: "Recent activity" }), _jsx("ul", { children: running.map((j) => (_jsxs("li", { children: [_jsx("span", { children: j.name }), _jsx(StatusBadge, { status: j.status })] }, j.jobId))) })] }))] }));
}
