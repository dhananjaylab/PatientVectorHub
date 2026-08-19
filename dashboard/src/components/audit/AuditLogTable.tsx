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
import { useState } from 'react'
import { useAuthStore } from '../../stores/useAuthStore'
import { hasExactRole } from '../../lib/rbac'
import {
  AUDIT_ACTIONS,
  useAuditLogs,
  useExportAuditLogs,
  type AuditAction,
  type AuditLogFilters,
  type ExportFormat,
} from '../../hooks/useAuditLogs'
import { getApiErrorMessage } from '../../lib/api'
import { Pagination } from '../common/Pagination'

const PAGE_SIZE = 50

export function AuditLogTable() {
  const { role } = useAuthStore()
  const canExport = hasExactRole(role, 'admin', 'auditor')
  const canFilterByUser = hasExactRole(role, 'admin', 'auditor')

  const [action, setAction] = useState<AuditAction | ''>('')
  const [userId, setUserId] = useState('')
  const [patientId, setPatientId] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [offset, setOffset] = useState(0)

  const filters: AuditLogFilters = {
    action: action || undefined,
    user_id: canFilterByUser && userId ? userId : undefined,
    patient_id: patientId || undefined,
    from_ts: fromDate ? new Date(`${fromDate}T00:00:00Z`).toISOString() : undefined,
    to_ts: toDate ? new Date(`${toDate}T23:59:59Z`).toISOString() : undefined,
    limit: PAGE_SIZE,
    offset,
  }

  const { data, isLoading, isError, error } = useAuditLogs(filters)
  const exportLogs = useExportAuditLogs()

  function onFilterChange() {
    setOffset(0)
  }

  function doExport(format: ExportFormat) {
    exportLogs.mutate({
      filters: { action: filters.action, user_id: filters.user_id, patient_id: filters.patient_id, from_ts: filters.from_ts, to_ts: filters.to_ts },
      format,
    })
  }

  return (
    <div className="audit-wrapper">
      <div className="audit-filters">
        <select
          value={action}
          onChange={(e) => {
            setAction(e.target.value as AuditAction | '')
            onFilterChange()
          }}
        >
          <option value="">All actions</option>
          {AUDIT_ACTIONS.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>

        {canFilterByUser && (
          <input
            className="mono"
            placeholder="Filter by user_id"
            value={userId}
            onChange={(e) => {
              setUserId(e.target.value)
              onFilterChange()
            }}
          />
        )}

        <input
          className="mono"
          placeholder="Filter by patient_id"
          value={patientId}
          onChange={(e) => {
            setPatientId(e.target.value)
            onFilterChange()
          }}
        />

        <input
          type="date"
          value={fromDate}
          onChange={(e) => {
            setFromDate(e.target.value)
            onFilterChange()
          }}
        />
        <span>to</span>
        <input
          type="date"
          value={toDate}
          onChange={(e) => {
            setToDate(e.target.value)
            onFilterChange()
          }}
        />

        {canExport && (
          <div className="audit-export">
            <button type="button" className="btn-ghost" disabled={exportLogs.isPending} onClick={() => doExport('csv')}>
              Export CSV
            </button>
            <button type="button" className="btn-ghost" disabled={exportLogs.isPending} onClick={() => doExport('json')}>
              Export JSON
            </button>
          </div>
        )}
      </div>

      {exportLogs.isError && <p className="field-error">{getApiErrorMessage(exportLogs.error)}</p>}
      {isLoading && <p className="loading-text">Loading audit logs…</p>}
      {isError && <p className="field-error">{getApiErrorMessage(error)}</p>}

      {data && (
        <>
          <table className="audit-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Action</th>
                <th>User</th>
                <th>Patient</th>
                <th>IP</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.logs.map((log) => (
                <tr key={log.id}>
                  <td className="mono">{new Date(log.created_at).toLocaleString()}</td>
                  <td>
                    <span className={`action-pill action-${log.action}`}>{log.action}</span>
                  </td>
                  <td className="mono">{log.user_id ? `${log.user_id.slice(0, 8)}…` : '—'}</td>
                  <td className="phi-cell" title="Hover to reveal">
                    {log.patient_id ?? '—'}
                  </td>
                  <td className="mono">{log.ip_address ?? '—'}</td>
                  <td className={log.status_code && log.status_code < 400 ? 'status-ok' : 'status-fail'}>
                    {log.status_code ?? '—'}
                  </td>
                </tr>
              ))}
              {data.logs.length === 0 && (
                <tr>
                  <td colSpan={6} className="empty-row">
                    No audit log entries match these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <Pagination total={data.total} limit={data.limit} offset={data.offset} onOffsetChange={setOffset} />
        </>
      )}
    </div>
  )
}
