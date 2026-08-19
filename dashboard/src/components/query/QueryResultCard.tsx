/**
 * dashboard/src/components/query/QueryResultCard.tsx
 *
 * New in Phase 9. chunk_text here is already de-identified by design —
 * vector-store/src/weaviate_store.py never stores raw PHI in chunk_text
 * (doc 05's Vector Store Schema: patient_id_hash = SHA256 only, no raw
 * PHI policy) — so unlike AuditLogTable's patient_id column, nothing
 * here needs the `.phi-cell` blur treatment.
 */
import type { QueryResultItem } from '../../hooks/useRAGQuery'

interface Props {
  result: QueryResultItem
  citationIndex?: number
}

export function QueryResultCard({ result, citationIndex }: Props) {
  const scorePct = Math.round(Math.max(0, Math.min(1, result.score)) * 100)
  return (
    <div className="query-result-card">
      <div className="query-result-score" style={{ width: `${scorePct}%` }} />
      <div className="query-result-body">
        <div className="query-result-header">
          {citationIndex != null && <span className="citation-badge">[{citationIndex}]</span>}
          <span className="doc-type-badge">{result.document_type.replace(/_/g, ' ')}</span>
          <span className="query-result-score-label mono">{scorePct}% match</span>
        </div>
        <p className="query-result-text">{result.chunk_text}</p>
        <p className="query-result-doc-id mono">{result.doc_id}</p>
      </div>
    </div>
  )
}
