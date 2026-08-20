import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
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
import { RoleGuard } from '../../components/common/RoleGuard';
import { StatusBadge } from '../../components/common/StatusBadge';
import { useNamespaceHealth } from '../../hooks/useAdmin';
import { getApiErrorMessage } from '../../lib/api';
function NamespaceHealthPanel() {
    const { data, isLoading, isError, error, dataUpdatedAt } = useNamespaceHealth();
    if (isLoading)
        return _jsx("p", { className: "loading-text", children: "Checking vector store health\u2026" });
    if (isError)
        return _jsx("p", { className: "field-error", children: getApiErrorMessage(error) });
    if (!data)
        return null;
    return (_jsxs("div", { className: "namespace-health-panel", children: [_jsxs("div", { className: "summary-card", children: [_jsx("span", { className: "summary-card-label", children: "Backend" }), _jsx("span", { className: "summary-card-value mono", children: data.backend })] }), _jsxs("div", { className: "summary-card", children: [_jsx("span", { className: "summary-card-label", children: "Status" }), _jsx("span", { className: "summary-card-value", children: _jsx(StatusBadge, { status: data.healthy ? 'active' : 'failed', label: data.healthy ? 'healthy' : 'unreachable' }) })] }), _jsxs("div", { className: "summary-card", children: [_jsx("span", { className: "summary-card-label", children: "Tenant" }), _jsxs("span", { className: "summary-card-value mono", children: [data.tenant_id.slice(0, 8), "\u2026"] })] }), _jsxs("p", { className: "placeholder-sub", children: ["Auto-refreshes every 15s. Last checked ", new Date(dataUpdatedAt).toLocaleTimeString(), "."] })] }));
}
export function AdminNamespacesPage() {
    return (_jsx(RoleGuard, { min: "engineer", children: _jsx(NamespaceHealthPanel, {}) }));
}
