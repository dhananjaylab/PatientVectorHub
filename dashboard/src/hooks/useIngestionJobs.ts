/**
 * dashboard/src/hooks/useIngestionJobs.ts
 *
 * Phase 9 — replaces the Phase 1 type stub. Two real, DIFFERENT wire
 * shapes exist for "an ingestion job" in this API, and this file's job
 * is to normalize both into one `IngestionJob*` shape so components
 * never have to know which endpoint they came from:
 *
 *  - GET /v1/ingest/jobs (list): routers/ingest.py's list_jobs has no
 *    response_model — it returns crud.list_ingestion_jobs()'s raw SELECT
 *    rows verbatim. Those rows have `id` (not `job_id`), no `name`... no
 *    wait, they DO have `name` (list SELECT includes it) but have NO
 *    `progress_pct`, NO `error_message`, NO `display_status` — that
 *    SELECT only pulls id/name/status/doc_count_total/doc_count_processed/
 *    doc_count_failed/created_at. See db/crud.py's list_ingestion_jobs
 *    docstring.
 *  - GET /v1/ingest/jobs/{id} and POST /v1/ingest/jobs (detail/create):
 *    go through routers/ingest.py's `_to_response()`, which returns
 *    `job_id` (not `id`), `progress_pct`, `error_message`, and the
 *    computed `display_status` — but NOT `name` (IngestJobResponse has
 *    no name field at all).
 *
 * Concretely: the list gives you a name but a stale/absent progress
 * number; the detail poll gives you a live progress number but no name.
 * JobProgressCard.tsx is the component that has to reconcile this — it
 * merges its `initial` (list-derived) prop with each detail poll rather
 * than replacing wholesale, specifically so `name` survives past the
 * first poll tick. See that component's docstring for the merge.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'

export type JobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'

export type DocumentType =
  | 'clinical_note'
  | 'lab_result'
  | 'imaging_report'
  | 'discharge_summary'
  | 'prescription'

export const DOCUMENT_TYPES: DocumentType[] = [
  'clinical_note',
  'lab_result',
  'imaging_report',
  'discharge_summary',
  'prescription',
]

/** Wire shape of one row from GET /v1/ingest/jobs's `jobs` array. */
interface RawJobListRow {
  id: string
  name: string
  status: JobStatus
  doc_count_total: number
  doc_count_processed: number
  doc_count_failed: number
  created_at: string | null
}

/** Wire shape of GET /v1/ingest/jobs/{id} and POST /v1/ingest/jobs. */
interface RawJobDetail {
  job_id: string
  status: JobStatus
  doc_count_total: number
  doc_count_processed: number
  doc_count_failed: number
  progress_pct: number
  error_message: string | null
  created_at: string | null
  display_status: string
}

export interface IngestionJobSummary {
  jobId: string
  name: string
  status: JobStatus
  docCountTotal: number
  docCountProcessed: number
  docCountFailed: number
  /** Not returned by the list endpoint — computed client-side. */
  progressPct: number
  createdAt: string | null
}

export interface IngestionJobDetail {
  jobId: string
  status: JobStatus
  displayStatus: string
  docCountTotal: number
  docCountProcessed: number
  docCountFailed: number
  progressPct: number
  errorMessage: string | null
  createdAt: string | null
}

function computeProgressPct(processed: number, total: number): number {
  const denom = Math.max(total, 1)
  return Math.round((processed / denom) * 1000) / 10
}

function normalizeListRow(row: RawJobListRow): IngestionJobSummary {
  return {
    jobId: row.id,
    name: row.name,
    status: row.status,
    docCountTotal: row.doc_count_total,
    docCountProcessed: row.doc_count_processed,
    docCountFailed: row.doc_count_failed,
    progressPct: computeProgressPct(row.doc_count_processed, row.doc_count_total),
    createdAt: row.created_at,
  }
}

function normalizeDetail(row: RawJobDetail): IngestionJobDetail {
  return {
    jobId: row.job_id,
    status: row.status,
    displayStatus: row.display_status,
    docCountTotal: row.doc_count_total,
    docCountProcessed: row.doc_count_processed,
    docCountFailed: row.doc_count_failed,
    progressPct: row.progress_pct,
    errorMessage: row.error_message,
    createdAt: row.created_at,
  }
}

export interface IngestionJobsPage {
  jobs: IngestionJobSummary[]
  total: number
  limit: number
  offset: number
}

export interface UseIngestionJobsParams {
  status?: JobStatus
  limit?: number
  offset?: number
}

/** Lists ingestion jobs. Polls every 5s so the list page shows live status
 * without a manual refresh, without polling as aggressively as the
 * per-job detail view (2s — see useJobDetail below) since a list of many
 * jobs is a heavier query than a single-row lookup. */
export function useIngestionJobs(params: UseIngestionJobsParams = {}) {
  const { status, limit = 20, offset = 0 } = params
  return useQuery<IngestionJobsPage>({
    queryKey: ['ingestion-jobs', status, limit, offset],
    queryFn: async () => {
      const { data } = await api.get<{ jobs: RawJobListRow[]; total: number; limit: number; offset: number }>(
        '/ingest/jobs',
        { params: { status, limit, offset } },
      )
      return { jobs: data.jobs.map(normalizeListRow), total: data.total, limit: data.limit, offset: data.offset }
    },
    refetchInterval: 5_000,
  })
}

/** Polls a single job's authoritative detail every 2s — this is the
 * source of truth for progress_pct/error_message/display_status, none
 * of which the list endpoint provides. */
export function useJobDetail(jobId: string | undefined) {
  return useQuery<IngestionJobDetail>({
    queryKey: ['ingestion-job', jobId],
    queryFn: async () => {
      const { data } = await api.get<RawJobDetail>(`/ingest/jobs/${jobId}`)
      return normalizeDetail(data)
    },
    refetchInterval: 2_000,
    enabled: !!jobId,
  })
}

export interface DocumentRefInput {
  source_path: string
  document_type: DocumentType
  patient_id: string
}

export interface CreateJobPayload {
  name: string
  source_type?: 's3_batch' | 'kafka_stream' | 'api_push'
  documents: DocumentRefInput[]
  embedding_model?: string
  chunk_size?: number
  chunk_overlap?: number
}

/** Requires engineer+ (require_min_role("engineer") — see routers/ingest.py).
 * Rate limited 100/min per doc 09 / ADR-015. */
export function useCreateJob() {
  const qc = useQueryClient()
  return useMutation<IngestionJobDetail, unknown, CreateJobPayload>({
    mutationFn: async (payload) => {
      const { data } = await api.post<RawJobDetail>('/ingest/jobs', payload)
      return normalizeDetail(data)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ingestion-jobs'] }),
  })
}
