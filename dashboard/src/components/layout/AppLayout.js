import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Link, NavLink } from 'react-router';
import { useAuthStore } from '../../stores/useAuthStore';
import { hasMinRole, roleLabel } from '../../lib/rbac';
import { logout, isAuthEnabled } from '../../lib/keycloak';
const NAV_ITEMS = [
    { to: '/dashboard', label: 'Dashboard', min: 'readonly' },
    { to: '/ingestion', label: 'Ingestion', min: 'engineer' },
    { to: '/query', label: 'Query', min: 'analyst' },
    { to: '/audit-logs', label: 'Audit Logs', min: 'auditor' },
    { to: '/monitoring', label: 'Monitoring', min: 'engineer' },
    { to: '/admin', label: 'Admin', min: 'admin' },
];
export function AppLayout({ children }) {
    const { email, role, tenantId } = useAuthStore();
    return (_jsxs("div", { className: "app-shell", children: [_jsxs("aside", { className: "app-sidebar", children: [_jsx(Link, { to: "/dashboard", className: "app-brand", children: "PatientVectorHub" }), _jsx("nav", { className: "app-nav", children: NAV_ITEMS.filter((item) => hasMinRole(role, item.min)).map((item) => (_jsx(NavLink, { to: item.to, className: ({ isActive }) => (isActive ? 'app-nav-link active' : 'app-nav-link'), children: item.label }, item.to))) })] }), _jsxs("div", { className: "app-main", children: [_jsxs("header", { className: "app-topbar", children: [_jsx("span", { className: "app-tenant mono", children: tenantId ? `tenant: ${tenantId.slice(0, 8)}…` : '' }), _jsxs("span", { className: "app-user", children: [email || (isAuthEnabled ? 'Loading…' : 'local-dev (auth disabled)'), _jsx("span", { className: "role-pill", children: roleLabel(role) })] }), isAuthEnabled && (_jsx("button", { type: "button", className: "btn-ghost", onClick: logout, children: "Log out" }))] }), _jsx("main", { className: "app-content", children: children })] })] }));
}
