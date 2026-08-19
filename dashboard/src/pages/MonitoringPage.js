import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * dashboard/src/pages/MonitoringPage.tsx
 *
 * New in Phase 9, deliberately a placeholder — flagged as a default
 * assumption before this phase's code was written, not discovered
 * midway. Prometheus/Grafana/Jaeger don't exist in this repo yet (that
 * work is the original 12-phase plan's Phase 10, Observability &
 * Security — api-gateway/src/main.py's lifespan() even has a
 * `# Phase 10 (Security): AuditLogMiddleware` comment marking the same
 * boundary). Rendering fabricated charts here would be actively
 * misleading on a HIPAA-adjacent ops page; the route/nav-guard/RBAC
 * floor (engineer+, matching doc 03) are wired now so Phase 10 only has
 * to fill in this one component, not touch routing.
 */
export function MonitoringPage() {
    return (_jsxs("div", { className: "monitoring-page", children: [_jsx("h1", { children: "Monitoring" }), _jsxs("div", { className: "placeholder-panel", children: [_jsx("p", { children: "Metrics dashboards (ingestion throughput, query latency P50/P95/P99, Kafka consumer lag, Weaviate index health) land in the Observability & Security phase, once Prometheus/Grafana are actually deployed." }), _jsxs("p", { className: "placeholder-sub", children: ["Until then, live vector-store health is available from the ", _jsx("strong", { children: "Dashboard" }), " and", ' ', _jsx("strong", { children: "Admin \u2192 Namespaces" }), " pages, which call the real", ' ', _jsx("code", { className: "mono", children: "GET /v1/admin/vector-store/namespaces" }), " endpoint."] })] })] }));
}
