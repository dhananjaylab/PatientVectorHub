import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * dashboard/src/pages/AuditLogPage.tsx
 * New in Phase 9. Thin page wrapper around AuditLogTable.
 */
import { AuditLogTable } from '../components/audit/AuditLogTable';
export function AuditLogPage() {
    return (_jsxs("div", { className: "audit-log-page", children: [_jsx("h1", { children: "Audit Trail" }), _jsx(AuditLogTable, {})] }));
}
