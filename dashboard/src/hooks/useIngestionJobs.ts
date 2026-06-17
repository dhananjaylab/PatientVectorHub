/**
 * Ingestion job hooks — Phase 1 type stubs.
 * Full implementation with 3s polling added in Phase 9.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'

export interface IngestionJob {
  job_id:              string
  name:                string
  status:              'queued' | 'running' | 'completed' | 'failed'
  doc_count_total:     number
  doc_count_processed: number
  doc_count_failed:    number
  progress_pct:        number
  throughput_per_sec:  number
  eta_seconds:         number | null
  error_message:       string | null
}

/** Poll all ingestion jobs every 3 seconds. */
export function useIngestionJobs() {
  return useQuery<IngestionJob[]>({
    queryKey:        ['ingestion-jobs'],
    queryFn:         () => api.get('/ingest/jobs').then(r => r.data.jobs),
    refetchInterval: 3_000,
  })
}

/** Poll a single job's detail every 2 seconds. */
export function useJobDetail(jobId: string) {
  return useQuery<IngestionJob>({
    queryKey:        ['ingestion-job', jobId],
    queryFn:         () => api.get(`/ingest/jobs/${jobId}`).then(r => r.data),
    refetchInterval: 2_000,
    enabled:         !!jobId,
  })
}

/** Mutation to create a new ingestion job. */
export function useCreateJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: object) =>
      api.post('/ingest/jobs', payload).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ingestion-jobs'] }),
  })
}
