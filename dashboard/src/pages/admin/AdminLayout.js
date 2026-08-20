import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * dashboard/src/pages/admin/AdminLayout.tsx
 *
 * New in Phase 9. Sub-nav tabs are individually role-gated rather than
 * the whole /admin/* subtree sharing one guard — matches
 * routers/admin.py's own module docstring precedent: "this file is an
 * organizational grouping (admin-surface routes), not a uniform-
 * permission boundary." App.tsx's top-level route guard for /admin/*
 * only requires engineer+ (the lowest floor of any page under this
 * layout, namespace health); AdminApiKeysPage / AdminUsersPage each
 * carry their own stricter admin-only Guard internally.
 */
import { NavLink, Outlet } from 'react-router';
export function AdminLayout() {
    return (_jsxs("div", { className: "admin-layout", children: [_jsx("h1", { children: "Admin" }), _jsxs("nav", { className: "sub-tabs", children: [_jsx(NavLink, { to: "/admin/api-keys", className: ({ isActive }) => (isActive ? 'sub-tab active' : 'sub-tab'), children: "API Keys" }), _jsx(NavLink, { to: "/admin/users", className: ({ isActive }) => (isActive ? 'sub-tab active' : 'sub-tab'), children: "Users" }), _jsx(NavLink, { to: "/admin/namespaces", className: ({ isActive }) => (isActive ? 'sub-tab active' : 'sub-tab'), children: "Vector Store" })] }), _jsx("div", { className: "admin-content", children: _jsx(Outlet, {}) })] }));
}
