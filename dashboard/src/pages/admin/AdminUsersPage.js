import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * dashboard/src/pages/admin/AdminUsersPage.tsx
 * New in Phase 9. Read-only per schemas/admin.py's UserListResponse —
 * there is no invite/deactivate endpoint in this API yet (doc 03's
 * "Invite, assign roles, deactivate" User Mgmt description is aspirational
 * beyond what routers/admin.py currently implements: GET /users only).
 */
import { ExactRoleGuard } from '../../components/common/RoleGuard';
import { StatusBadge } from '../../components/common/StatusBadge';
import { useAdminUsers } from '../../hooks/useAdmin';
import { getApiErrorMessage } from '../../lib/api';
import { roleLabel } from '../../lib/rbac';
function UsersTable() {
    const { data: users, isLoading, isError, error } = useAdminUsers();
    if (isLoading)
        return _jsx("p", { className: "loading-text", children: "Loading users\u2026" });
    if (isError)
        return _jsx("p", { className: "field-error", children: getApiErrorMessage(error) });
    if (!users || users.length === 0)
        return _jsx("p", { className: "empty-state", children: "No users found for this tenant." });
    return (_jsxs("table", { className: "admin-table", children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Email" }), _jsx("th", { children: "Role" }), _jsx("th", { children: "Status" }), _jsx("th", { children: "Last login" }), _jsx("th", { children: "Created" })] }) }), _jsx("tbody", { children: users.map((u) => (_jsxs("tr", { children: [_jsx("td", { children: u.email }), _jsx("td", { children: roleLabel(u.role) }), _jsx("td", { children: _jsx(StatusBadge, { status: u.is_active ? 'active' : 'revoked', label: u.is_active ? 'active' : 'inactive' }) }), _jsx("td", { className: "mono", children: u.last_login ? new Date(u.last_login).toLocaleString() : 'never' }), _jsx("td", { className: "mono", children: new Date(u.created_at).toLocaleDateString() })] }, u.id))) })] }));
}
export function AdminUsersPage() {
    return (_jsx(ExactRoleGuard, { allow: ['admin'], children: _jsx(UsersTable, {}) }));
}
