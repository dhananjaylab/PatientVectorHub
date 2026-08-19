/**
 * dashboard/src/components/query/QueryForm.tsx
 *
 * New in Phase 9. Provider selector defaults to "Default" (omits
 * llm_provider from the request entirely) rather than pre-selecting
 * "anthropic" — see hooks/useRAGQuery.ts's docstring for why hardcoding
 * a default here would risk drifting from rag-engine's own
 * LLM_DEFAULT_PROVIDER setting. Document-type filter checkboxes are the
 * only filter offered — date_range/cohort_filter aren't in the real
 * QueryFilters schema yet (ADR-014 §3).
 */
import { useState, type FormEvent } from 'react'
import { DOCUMENT_TYPES, type DocumentType } from '../../hooks/useIngestionJobs'
import { useRAGQuery, type LlmProvider } from '../../hooks/useRAGQuery'
import { getApiErrorMessage } from '../../lib/api'
import { QueryResultCard } from './QueryResultCard'

const PROVIDERS: { value: LlmProvider | ''; label: string }[] = [
  { value: '', label: 'Default (server-configured)' },
  { value: 'anthropic', label: 'Anthropic Claude' },
  { value: 'openai', label: 'OpenAI GPT' },
  { value: 'gemini', label: 'Google Gemini' },
]

export function QueryForm() {
  const { mutate, isPending, data, isError, error } = useRAGQuery()
  const [text, setText] = useState('')
  const [topK, setTopK] = useState(10)
  const [provider, setProvider] = useState<LlmProvider | ''>('')
  const [docTypes, setDocTypes] = useState<Set<DocumentType>>(new Set())

  function toggleDocType(t: DocumentType) {
    setDocTypes((prev) => {
      const next = new Set(prev)
      if (next.has(t)) {
        next.delete(t)
      } else {
        next.add(t)
      }
      return next
    })
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (text.trim().length < 3) return
    mutate({
      query_text: text.trim(),
      top_k: topK,
      llm_provider: provider || undefined,
      filters: docTypes.size > 0 ? { document_types: Array.from(docTypes) } : undefined,
    })
  }

  return (
    <div className="query-page">
      <form onSubmit={onSubmit} className="query-form">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Clinical query — e.g. patients with type 2 diabetes and recent elevated HbA1c"
          rows={4}
          minLength={3}
          maxLength={2000}
        />

        <div className="query-doc-type-filters">
          {DOCUMENT_TYPES.map((t) => (
            <label key={t} className="chip-checkbox">
              <input type="checkbox" checked={docTypes.has(t)} onChange={() => toggleDocType(t)} />
              {t.replace(/_/g, ' ')}
            </label>
          ))}
        </div>

        <div className="query-controls">
          <select value={provider} onChange={(e) => setProvider(e.target.value as LlmProvider | '')}>
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
          <label className="top-k-field">
            top_k
            <input type="number" min={1} max={50} value={topK} onChange={(e) => setTopK(Number(e.target.value))} />
          </label>
          <button type="submit" className="btn-primary" disabled={isPending || text.trim().length < 3}>
            {isPending ? 'Querying…' : 'Run Query'}
          </button>
        </div>
      </form>

      {isError && <p className="field-error">{getApiErrorMessage(error)}</p>}

      {data && (
        <div className="query-results">
          <div className="query-answer">
            <div className="query-answer-header">
              <h3>Answer</h3>
              <span className="mono query-latency">{data.latency_ms}ms</span>
            </div>
            <p>{data.answer}</p>
            {data.citations.length > 0 && (
              <p className="query-citations mono">
                Sources: {data.citations.map((c) => `[${c.index}] ${c.document_type}`).join('  ')}
              </p>
            )}
          </div>

          <div className="query-result-list">
            {data.results.map((r, i) => (
              <QueryResultCard key={`${r.doc_id}-${i}`} result={r} citationIndex={data.citations.find((c) => c.doc_id === r.doc_id)?.index} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
