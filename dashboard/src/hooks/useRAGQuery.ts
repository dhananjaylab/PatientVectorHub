/**
 * dashboard/src/hooks/useRAGQuery.ts
 *
 * Phase 9 — replaces the Phase 1 type stub, which was ahead of the real
 * backend in two ways worth calling out explicitly (both against
 * api-gateway/src/schemas/query.py, verified this phase):
 *
 *  1. QueryFilters only has `document_types` on the wire.
 *     `date_range`/`cohort_filter` were in the original doc-32 sketch
 *     and in the Phase 1 stub's TS type, but ADR-014 §3 deferred them —
 *     vector-store/src/weaviate_store.py's _build_filter() doesn't
 *     implement them. Sending them would be silently ignored server-side
 *     (Pydantic drops unknown-to-QueryFilters fields), which is worse
 *     than not offering the UI for them at all — QueryForm.tsx doesn't
 *     render date-range/cohort inputs this phase.
 *  2. Citation's field is `document_type`, not `type` — the stub's
 *     `{ index, doc_id, type }` would have deserialized with `type`
 *     always `undefined` against the real response.
 *
 * llm_provider is optional (`string | null`, no default) because
 * schemas/query.py's own docstring explains why: the real default lives
 * in rag-engine/src/config.py's LLM_DEFAULT_PROVIDER, resolved
 * server-side in LLMRouter.complete(). Hardcoding "anthropic" as this
 * hook's default would duplicate that and could drift from it silently
 * — QueryForm.tsx's provider selector defaults to an empty/"Default"
 * option that omits the field entirely rather than picking a provider
 * for the person.
 */
import { useMutation } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { DocumentType } from './useIngestionJobs'

export type LlmProvider = 'openai' | 'anthropic' | 'gemini'

export interface QueryFilters {
  document_types?: DocumentType[]
}

export interface QueryRequest {
  query_text: string
  filters?: QueryFilters
  top_k: number
  llm_provider?: LlmProvider
}

export interface QueryResultItem {
  doc_id: string
  chunk_text: string
  score: number
  document_type: string
}

export interface Citation {
  index: number
  doc_id: string
  document_type: string
}

export interface QueryResponse {
  query_id: string
  answer: string
  citations: Citation[]
  results: QueryResultItem[]
  latency_ms: number
}

/** Requires analyst+ (require_min_role("analyst")). Rate limited
 * 1000/min per doc 09 / ADR-015 — the highest limit in this API,
 * reflecting query as the primary end-user-facing action. */
export function useRAGQuery() {
  return useMutation<QueryResponse, unknown, QueryRequest>({
    mutationFn: async (req) => {
      const { data } = await api.post<QueryResponse>('/query', req)
      return data
    },
  })
}
