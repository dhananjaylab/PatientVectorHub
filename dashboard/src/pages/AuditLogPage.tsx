/**
 * dashboard/src/pages/AuditLogPage.tsx
 * New in Phase 9. Thin page wrapper around AuditLogTable.
 */
import { AuditLogTable } from '../components/audit/AuditLogTable'

export function AuditLogPage() {
  return (
    <div className="audit-log-page">
      <h1>Audit Trail</h1>
      <AuditLogTable />
    </div>
  )
}
