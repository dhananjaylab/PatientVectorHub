/**
 * dashboard/src/components/common/Pagination.tsx
 *
 * Offset/limit pager — matches the `{ total, limit, offset }` envelope
 * shared by GET /v1/ingest/jobs and GET /v1/audit/logs (db/crud.py's
 * list_ingestion_jobs / list_audit_logs both return this same shape).
 */
interface Props {
  total: number
  limit: number
  offset: number
  onOffsetChange: (next: number) => void
}

export function Pagination({ total, limit, offset, onOffsetChange }: Props) {
  const page = Math.floor(offset / limit) + 1
  const pageCount = Math.max(1, Math.ceil(total / limit))
  const hasPrev = offset > 0
  const hasNext = offset + limit < total

  if (total <= limit && offset === 0) return null

  return (
    <div className="pagination">
      <button type="button" disabled={!hasPrev} onClick={() => onOffsetChange(Math.max(0, offset - limit))}>
        ← Prev
      </button>
      <span>
        Page {page} / {pageCount} · {total.toLocaleString()} total
      </span>
      <button type="button" disabled={!hasNext} onClick={() => onOffsetChange(offset + limit)}>
        Next →
      </button>
    </div>
  )
}
