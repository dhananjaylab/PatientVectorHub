/**
 * dashboard/src/pages/IngestionPage.tsx
 * New in Phase 9. Job cards poll live detail via JobProgressCard itself.
 */
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useIngestionJobs, type JobStatus } from '../hooks/useIngestionJobs'
import { JobProgressCard } from '../components/ingestion/JobProgressCard'
import { Pagination } from '../components/common/Pagination'
import { getApiErrorMessage } from '../lib/api'

const STATUS_FILTERS: (JobStatus | '')[] = ['', 'queued', 'running', 'completed', 'failed', 'cancelled']
const PAGE_SIZE = 12

export function IngestionPage() {
  const [status, setStatus] = useState<JobStatus | ''>('')
  const [offset, setOffset] = useState(0)
  const [searchParams] = useSearchParams()
  const highlightId = searchParams.get('highlight')

  const { data, isLoading, isError, error } = useIngestionJobs({
    status: status || undefined,
    limit: PAGE_SIZE,
    offset,
  })

  return (
    <div className="ingestion-page">
      <div className="page-header">
        <h1>Ingestion Jobs</h1>
        <Link to="/ingestion/new" className="btn-primary">
          New Batch Job
        </Link>
      </div>

      <div className="status-filter-row">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s || 'all'}
            type="button"
            className={status === s ? 'tab-btn active' : 'tab-btn'}
            onClick={() => {
              setStatus(s)
              setOffset(0)
            }}
          >
            {s || 'All'}
          </button>
        ))}
      </div>

      {isLoading && <p className="loading-text">Loading jobs…</p>}
      {isError && <p className="field-error">{getApiErrorMessage(error)}</p>}

      {data && data.jobs.length === 0 && (
        <div className="empty-state">
          <p>No ingestion jobs yet.</p>
          <Link to="/ingestion/new" className="btn-ghost">
            Start your first ingestion pipeline →
          </Link>
        </div>
      )}

      <div className="job-card-grid">
        {data?.jobs.map((job) => (
          <div key={job.jobId} className={job.jobId === highlightId ? 'job-card-highlight' : undefined}>
            <JobProgressCard job={job} />
          </div>
        ))}
      </div>

      {data && <Pagination total={data.total} limit={data.limit} offset={data.offset} onOffsetChange={setOffset} />}
    </div>
  )
}
