import { describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import { createTestQueryClient } from '../../test/testUtils'
import { api } from '../../lib/api'
import { useIngestionJobs, useJobDetail } from '../useIngestionJobs'

vi.mock('../../lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={createTestQueryClient()}>{children}</QueryClientProvider>
}

describe('useIngestionJobs (list)', () => {
  it('normalizes list rows — id -> jobId, and computes progressPct client-side (list SELECT has no progress_pct column)', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      data: {
        jobs: [
          {
            id: 'job-1',
            name: 'nightly-batch',
            status: 'running',
            doc_count_total: 200,
            doc_count_processed: 50,
            doc_count_failed: 0,
            created_at: '2026-08-01T00:00:00Z',
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      },
    })

    const { result } = renderHook(() => useIngestionJobs(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.jobs[0]).toEqual({
      jobId: 'job-1',
      name: 'nightly-batch',
      status: 'running',
      docCountTotal: 200,
      docCountProcessed: 50,
      docCountFailed: 0,
      progressPct: 25, // 50/200 * 100
      createdAt: '2026-08-01T00:00:00Z',
    })
    expect(api.get).toHaveBeenCalledWith('/ingest/jobs', { params: { status: undefined, limit: 20, offset: 0 } })
  })

  it('does not divide by zero when doc_count_total is 0 (job just created, before set_job_doc_count_total runs)', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      data: {
        jobs: [{ id: 'job-2', name: 'x', status: 'queued', doc_count_total: 0, doc_count_processed: 0, doc_count_failed: 0, created_at: null }],
        total: 1,
        limit: 20,
        offset: 0,
      },
    })
    const { result } = renderHook(() => useIngestionJobs(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.jobs[0].progressPct).toBe(0)
  })
})

describe('useJobDetail', () => {
  it('normalizes detail rows — job_id -> jobId, passes through the real progress_pct/display_status', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      data: {
        job_id: 'job-1',
        status: 'completed',
        doc_count_total: 200,
        doc_count_processed: 198,
        doc_count_failed: 2,
        progress_pct: 99.0,
        error_message: null,
        created_at: '2026-08-01T00:00:00Z',
        display_status: 'completed_with_errors',
      },
    })

    const { result } = renderHook(() => useJobDetail('job-1'), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual({
      jobId: 'job-1',
      status: 'completed',
      displayStatus: 'completed_with_errors',
      docCountTotal: 200,
      docCountProcessed: 198,
      docCountFailed: 2,
      progressPct: 99.0,
      errorMessage: null,
      createdAt: '2026-08-01T00:00:00Z',
    })
  })

  it('does not fire when jobId is undefined (enabled: false)', () => {
    renderHook(() => useJobDetail(undefined), { wrapper })
    expect(api.get).not.toHaveBeenCalled()
  })
})
