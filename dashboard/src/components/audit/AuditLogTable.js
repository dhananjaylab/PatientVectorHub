import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
/**
 * dashboard/src/components/audit/AuditLogTable.tsx
 *
 * New in Phase 9. Two RBAC-driven UI decisions worth flagging (both
 * documented at length in hooks/useAuditLogs.ts, repeated briefly here
 * since they change what this component renders):
 *   - The `user_id` filter input only renders for admin/auditor —
 *     showing it to an analyst/engineer would silently do nothing
 *     (routers/audit.py forces their own user_id regardless of what
 *     they type), which is worse UX than omitting the field.
 *   - The Export button only renders for admin/auditor (exact role
 *     match, matching require_role("admin", "auditor") on
 *     GET /logs/export — stricter than this table's own require_min_role
 *     ("auditor") read floor).
 * patient_id is blurred via index.css's existing `.phi-cell` (hover to
 * reveal) — the value itself is never masked by the API (see
 * schemas/audit.py's docstring), this is purely a rendering choice.
 */
import { useState } from 'react';
import { useAuthStore } from '../../stores/useAuthStore';
import { hasExactRole } from '../../lib/rbac';
import { AUDIT_ACTIONS, useAuditLogs, useExportAuditLogs, } from '../../hooks/useAuditLogs';
import { getApiErrorMessage } from '../../lib/api';
import { Pagination } from '../common/Pagination';
const PAGE_SIZE = 50;
export function AuditLogTable() {
    const { role } = useAuthStore();
    const canExport = hasExactRole(role, 'admin', 'auditor');
    const canFilterByUser = hasExactRole(role, 'admin', 'auditor');
    const [action, setAction] = useState('');
    const [userId, setUserId] = useState('');
    const [patientId, setPatientId] = useState('');
    const [fromDate, setFromDate] = useState('');
    const [toDate, setToDate] = useState('');
    const [offset, setOffset] = useState(0);
    const filters = {
        action: action || undefined,
        user_id: canFilterByUser && userId ? userId : undefined,
        patient_id: patientId || undefined,
        from_ts: fromDate ? new Date(`${fromDate}T00:00:00Z`).toISOString() : undefined,
        to_ts: toDate ? new Date(`${toDate}T23:59:59Z`).toISOString() : undefined,
        limit: PAGE_SIZE,
        offset,
    };
    const { data, isLoading, isError, error } = useAuditLogs(filters);
    const exportLogs = useExportAuditLogs();
    function onFilterChange() {
        setOffset(0);
    }
    function doExport(format) {
        exportLogs.mutate({
            filters: { action: filters.action, user_id: filters.user_id, patient_id: filters.patient_id, from_ts: filters.from_ts, to_ts: filters.to_ts },
            format,
        });
    }
    return (_jsxs("div", { className: "audit-wrapper", children: [_jsxs("div", { className: "audit-filters", children: [_jsxs("select", { value: action, onChange: (e) => {
                            setAction(e.target.value);
                            onFilterChange();
                        }, children: [_jsx("option", { value: "", children: "All actions" }), AUDIT_ACTIONS.map((a) => (_jsx("option", { value: a, children: a }, a)))] }), canFilterByUser && (_jsx("input", { className: "mono", placeholder: "Filter by user_id", value: userId, onChange: (e) => {
                            setUserId(e.target.value);
                            onFilterChange();
                        } })), _jsx("input", { className: "mono", placeholder: "Filter by patient_id", value: patientId, onChange: (e) => {
                            setPatientId(e.target.value);
                            onFilterChange();
                        } }), _jsx("input", { type: "date", value: fromDate, onChange: (e) => {
                            setFromDate(e.target.value);
                            onFilterChange();
                        } }), _jsx("span", { children: "to" }), _jsx("input", { type: "date", value: toDate, onChange: (e) => {
                            setToDate(e.target.value);
                            onFilterChange();
                        } }), canExport && (_jsxs("div", { className: "audit-export", children: [_jsx("button", { type: "button", className: "btn-ghost", disabled: exportLogs.isPending, onClick: () => doExport('csv'), children: "Export CSV" }), _jsx("button", { type: "button", className: "btn-ghost", disabled: exportLogs.isPending, onClick: () => doExport('json'), children: "Export JSON" })] }))] }), exportLogs.isError && _jsx("p", { className: "field-error", children: getApiErrorMessage(exportLogs.error) }), isLoading && _jsx("p", { className: "loading-text", children: "Loading audit logs\u2026" }), isError && _jsx("p", { className: "field-error", children: getApiErrorMessage(error) }), data && (_jsxs(_Fragment, { children: [_jsxs("table", { className: "audit-table", children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Timestamp" }), _jsx("th", { children: "Action" }), _jsx("th", { children: "User" }), _jsx("th", { children: "Patient" }), _jsx("th", { children: "IP" }), _jsx("th", { children: "Status" })] }) }), _jsxs("tbody", { children: [data.logs.map((log) => (_jsxs("tr", { children: [_jsx("td", { className: "mono", children: new Date(log.created_at).toLocaleString() }), _jsx("td", { children: _jsx("span", { className: `action-pill action-${log.action}`, children: log.action }) }), _jsx("td", { className: "mono", children: log.user_id ? `${log.user_id.slice(0, 8)}…` : '—' }), _jsx("td", { className: "phi-cell", title: "Hover to reveal", children: log.patient_id ?? '—' }), _jsx("td", { className: "mono", children: log.ip_address ?? '—' }), _jsx("td", { className: log.status_code && log.status_code < 400 ? 'status-ok' : 'status-fail', children: log.status_code ?? '—' })] }, log.id))), data.logs.length === 0 && (_jsx("tr", { children: _jsx("td", { colSpan: 6, className: "empty-row", children: "No audit log entries match these filters." }) }))] })] }), _jsx(Pagination, { total: data.total, limit: data.limit, offset: data.offset, onOffsetChange: setOffset })] }))] }));
}
