import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
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
import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { initKeycloak, keycloak } from './lib/keycloak';
import { useAuthStore } from './stores/useAuthStore';
import { ROLE_PRIORITY } from './lib/rbac';
import { RoleGuard } from './components/common/RoleGuard';
import { AppLayout } from './components/layout/AppLayout';
import { DashboardPage } from './pages/DashboardPage';
import { IngestionPage } from './pages/IngestionPage';
import { NewJobPage } from './pages/NewJobPage';
import { QueryPage } from './pages/QueryPage';
import { AuditLogPage } from './pages/AuditLogPage';
import { MonitoringPage } from './pages/MonitoringPage';
import { AdminLayout } from './pages/admin/AdminLayout';
import { AdminApiKeysPage } from './pages/admin/AdminApiKeysPage';
import { AdminUsersPage } from './pages/admin/AdminUsersPage';
import { AdminNamespacesPage } from './pages/admin/AdminNamespacesPage';
import { NotFoundPage } from './pages/NotFoundPage';
const qc = new QueryClient({
    defaultOptions: {
        queries: { retry: 1, staleTime: 30_000 },
    },
});
export default function App() {
    const [ready, setReady] = useState(false);
    const { setUser } = useAuthStore();
    useEffect(() => {
        initKeycloak()
            .then((authed) => {
            if (authed && keycloak.tokenParsed) {
                const t = keycloak.tokenParsed;
                const roles = t['realm_access']?.roles ?? [];
                const role = (ROLE_PRIORITY.find((r) => roles.includes(r)) ?? 'readonly');
                setUser({
                    userId: String(t['sub'] ?? ''),
                    email: String(t['email'] ?? ''),
                    role,
                    tenantId: String(t['tenant_id'] ?? ''),
                });
            }
            setReady(true);
        })
            .catch(() => setReady(true));
    }, [setUser]);
    if (!ready) {
        return _jsx("div", { className: "auth-loading", children: "Authenticating via Keycloak\u2026" });
    }
    return (_jsx(QueryClientProvider, { client: qc, children: _jsx(BrowserRouter, { children: _jsx(AppLayout, { children: _jsxs(Routes, { children: [_jsx(Route, { path: "/", element: _jsx(Navigate, { to: "/dashboard", replace: true }) }), _jsx(Route, { path: "/dashboard", element: _jsx(DashboardPage, {}) }), _jsx(Route, { path: "/ingestion", element: _jsx(RoleGuard, { min: "engineer", children: _jsx(IngestionPage, {}) }) }), _jsx(Route, { path: "/ingestion/new", element: _jsx(RoleGuard, { min: "engineer", children: _jsx(NewJobPage, {}) }) }), _jsx(Route, { path: "/query", element: _jsx(RoleGuard, { min: "analyst", children: _jsx(QueryPage, {}) }) }), _jsx(Route, { path: "/audit-logs", element: _jsx(RoleGuard, { min: "auditor", children: _jsx(AuditLogPage, {}) }) }), _jsx(Route, { path: "/monitoring", element: _jsx(RoleGuard, { min: "engineer", children: _jsx(MonitoringPage, {}) }) }), _jsxs(Route, { path: "/admin", element: _jsx(RoleGuard, { min: "engineer", children: _jsx(AdminLayout, {}) }), children: [_jsx(Route, { index: true, element: _jsx(Navigate, { to: "/admin/api-keys", replace: true }) }), _jsx(Route, { path: "api-keys", element: _jsx(AdminApiKeysPage, {}) }), _jsx(Route, { path: "users", element: _jsx(AdminUsersPage, {}) }), _jsx(Route, { path: "namespaces", element: _jsx(AdminNamespacesPage, {}) })] }), _jsx(Route, { path: "*", element: _jsx(NotFoundPage, {}) })] }) }) }) }));
}
