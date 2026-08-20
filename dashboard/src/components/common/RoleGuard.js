import { jsxs as _jsxs } from "react/jsx-runtime";
import { useAuthStore } from '../../stores/useAuthStore';
import { hasMinRole, hasExactRole } from '../../lib/rbac';
export function RoleGuard({ children, min }) {
    const { role } = useAuthStore();
    if (!hasMinRole(role, min)) {
        return _jsxs("div", { className: "error-403", children: ["403 \u2014 role '", role, "' cannot access this page."] });
    }
    return children;
}
export function ExactRoleGuard({ children, allow }) {
    const { role } = useAuthStore();
    if (!hasExactRole(role, ...allow)) {
        return _jsxs("div", { className: "error-403", children: ["403 \u2014 role '", role, "' cannot access this page."] });
    }
    return children;
}
