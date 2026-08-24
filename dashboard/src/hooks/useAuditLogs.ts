/**
 * dashboard/src/hooks/useAuditLogs.ts
 *
 * New in Phase 9 (Phase 1 had no audit hooks at all — the audit router
 * itself is Phase 8/ADR-015 work). Field names below are a direct copy
 * of schemas/audit.py's AuditLogEntry — patient_id arrives as a plain
 * string, NOT pre-blurred; see that schema's own docstring for why
 * (blurring is a frontend rendering concern, `.phi-cell` in index.css,
 * not something the API degrades). AuditLogTable.tsx is the component
 * that applies the blur.
 *
 * Role behavior worth knowing when wiring UI around this: GET /logs
 * silently self-scopes non-admin/auditor callers to their own user_id
 * (routers/audit.py's `_resolve_effective_user_id`) rather than
 * rejecting a `user_id` filter they tried to set — so an analyst who
 * types someone else's user_id into a filter field (if such a field
 * were ever shown to them) would just get their own logs back, not an
 * error and not the other person's data. AuditLogTable.tsx only renders
 * the user_id filter input for admin/auditor for exactly this reason —
 * showing it to an analyst would silently do nothing, which is worse UX
 * than not offering it.
 */
import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'

export interface AuditLogEntry {
  id: string
  user_id: string | null
  action: string
  patient_id: string | null
  ip_address: string | null
  request_id: string | null
  status_code: number | null
  created_at: string
}

export interface AuditLogListResponse {
  logs: AuditLogEntry[]
  total: number
  limit: number
  offset: number
}

export const AUDIT_ACTIONS = [
  'document_query',
  'document_ingest',
  'phi_reveal',
  'api_key_create',
  'api_key_revoke',
  'data_export',
  // Phase 10 / ADR-017: migration 005 added this to the backend's
  // action CHECK constraint; AuditLogMiddleware writes it for 403 RBAC
  // denials (never bare 401s -- see that middleware's own docstring for
  // the RLS-driven reason).
  'access_denied',
] as const
export type AuditAction = (typeof AUDIT_ACTIONS)[number]

export interface AuditLogFilters {
  action?: AuditAction | ''
  user_id?: string
  patient_id?: string
  from_ts?: string
  to_ts?: string
  limit?: number
  offset?: number
}

/** Requires auditor+ at minimum (require_min_role("auditor") — everyone
 * except readonly passes the gate; see routers/audit.py's module
 * docstring for the self-scoping behavior below that). Rate limited
 * 200/min. */
export function useAuditLogs(filters: AuditLogFilters) {
  const { limit = 50, offset = 0, ...rest } = filters
  return useQuery<AuditLogListResponse>({
    queryKey: ['audit-logs', rest, limit, offset],
    queryFn: async () => {
      const params = Object.fromEntries(
        Object.entries({ ...rest, limit, offset }).filter(([, v]) => v !== '' && v !== undefined),
      )
      const { data } = await api.get<AuditLogListResponse>('/audit/logs', { params })
      return data
    },
    // No polling — audit review is a point-in-time pull, not a live
    // dashboard; matches doc 03's "Audit Trail" page description
    // (filtered browsing, not a live feed) and avoids re-querying a
    // 10k+ row table every few seconds on a page an auditor may leave
    // open for a long session.
  })
}

export type ExportFormat = 'csv' | 'json'

/** Requires exact admin/auditor role (require_role("admin", "auditor") —
 * stricter than GET /logs's require_min_role("auditor"), no
 * self-scoping fallback: analyst/engineer get a 403, not their own
 * data). Rate limited 10/min — the tightest limit in this API, since
 * this is a full compliance-evidence pull, not routine browsing. */
export function useExportAuditLogs() {
  return useMutation<void, unknown, { filters: Omit<AuditLogFilters, 'limit' | 'offset'>; format: ExportFormat }>({
    mutationFn: async ({ filters, format }) => {
      const params = Object.fromEntries(
        Object.entries({ ...filters, format }).filter(([, v]) => v !== '' && v !== undefined),
      )
      const response = await api.get<Blob>('/audit/logs/export', { params, responseType: 'blob' })
      const disposition = response.headers['content-disposition'] as string | undefined
      const match = disposition?.match(/filename="?([^"]+)"?/)
      const filename = match?.[1] ?? `audit-logs.${format}`

      const url = URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    },
  })
}

/**
 * Phase 10 / ADR-017. Closes the gap Phase 9's own ADR-016 flagged by
 * name: `.phi-cell`'s hover-to-reveal was purely a CSS effect with no
 * audit trail, because Phase 9 didn't own backend scope. Same
 * require_min_role("auditor") floor as useAuditLogs above — a caller
 * can only ever reveal a patient_id they already legitimately fetched
 * via that same endpoint. Fire-and-forget from the caller's
 * perspective (204 No Content) — AuditLogTable.tsx calls `.mutate(...)`,
 * not `.mutateAsync(...)`, and doesn't block the hover interaction on
 * this resolving.
 */
export function useLogPhiReveal() {
  return useMutation<void, unknown, { auditLogId: string; patientId: string }>({
    mutationFn: async ({ auditLogId, patientId }) => {
      await api.post('/audit/phi-reveal', {
        audit_log_id: auditLogId,
        patient_id: patientId,
      })
    },
  })
}
