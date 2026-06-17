/**
 * RAG query mutation hook — Phase 1 type stubs.
 * Full implementation wired in Phase 9.
 */
import { useMutation } from '@tanstack/react-query'
import { api } from '../lib/api'

export interface QueryFilters {
  document_types?: string[]
  date_range?:     { from: string; to: string }
  cohort_filter?:  Record<string, string>
}

export interface QueryRequest {
  query_text:   string
  filters?:     QueryFilters
  top_k:        number
  llm_provider: 'openai' | 'anthropic' | 'gemini'
}

export interface QueryResult {
  doc_id:        string
  chunk_text:    string
  score:         number
  document_type: string
}

export interface QueryResponse {
  query_id:   string
  answer:     string
  citations:  { index: number; doc_id: string; type: string }[]
  results:    QueryResult[]
  latency_ms: number
}

export function useRAGQuery() {
  return useMutation<QueryResponse, Error, QueryRequest>({
    mutationFn: req => api.post('/query', req).then(r => r.data),
  })
}
