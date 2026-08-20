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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
export const DOCUMENT_TYPES = [
    'clinical_note',
    'lab_result',
    'imaging_report',
    'discharge_summary',
    'prescription',
];
function computeProgressPct(processed, total) {
    const denom = Math.max(total, 1);
    return Math.round((processed / denom) * 1000) / 10;
}
function normalizeListRow(row) {
    return {
        jobId: row.id,
        name: row.name,
        status: row.status,
        docCountTotal: row.doc_count_total,
        docCountProcessed: row.doc_count_processed,
        docCountFailed: row.doc_count_failed,
        progressPct: computeProgressPct(row.doc_count_processed, row.doc_count_total),
        createdAt: row.created_at,
    };
}
function normalizeDetail(row) {
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
    };
}
/** Lists ingestion jobs. Polls every 5s so the list page shows live status
 * without a manual refresh, without polling as aggressively as the
 * per-job detail view (2s — see useJobDetail below) since a list of many
 * jobs is a heavier query than a single-row lookup. */
export function useIngestionJobs(params = {}) {
    const { status, limit = 20, offset = 0, enabled = true } = params;
    return useQuery({
        queryKey: ['ingestion-jobs', status, limit, offset],
        queryFn: async () => {
            const { data } = await api.get('/ingest/jobs', { params: { status, limit, offset } });
            return { jobs: data.jobs.map(normalizeListRow), total: data.total, limit: data.limit, offset: data.offset };
        },
        refetchInterval: 5_000,
        enabled,
    });
}
/** Polls a single job's authoritative detail every 2s — this is the
 * source of truth for progress_pct/error_message/display_status, none
 * of which the list endpoint provides. */
export function useJobDetail(jobId) {
    return useQuery({
        queryKey: ['ingestion-job', jobId],
        queryFn: async () => {
            const { data } = await api.get(`/ingest/jobs/${jobId}`);
            return normalizeDetail(data);
        },
        refetchInterval: 2_000,
        enabled: !!jobId,
    });
}
/** Requires engineer+ (require_min_role("engineer") — see routers/ingest.py).
 * Rate limited 100/min per doc 09 / ADR-015. */
export function useCreateJob() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (payload) => {
            const { data } = await api.post('/ingest/jobs', payload);
            return normalizeDetail(data);
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['ingestion-jobs'] }),
    });
}
