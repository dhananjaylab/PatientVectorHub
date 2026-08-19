/**
 * dashboard/src/components/ingestion/JobProgressCard.tsx
 *
 * New in Phase 9. `initial` comes from useIngestionJobs()'s list
 * (has `name`, no live progress_pct/error_message). Each 2s poll via
 * useJobDetail() returns the opposite (`progress_pct`/`error_message`,
 * no `name`). We MERGE rather than replace — `{ ...initial, ...detail }`
 * — specifically so `name` doesn't disappear from the card the moment
 * the first poll resolves. Replacing wholesale (`data ?? initial`, the
 * original doc 35 sketch's pattern) would show a blank job name after
 * ~2 seconds on every card; caught by writing
 * JobProgressCard.test.tsx's second-poll-tick assertion before shipping
 * this component (see that test file).
 */
import { useJobDetail, type IngestionJobDetail, type IngestionJobSummary } from '../../hooks/useIngestionJobs'
import { StatusBadge } from '../common/StatusBadge'

const PHASES = ['Reading', 'Chunking', 'Embedding', 'Storing']

interface Props {
  job: IngestionJobSummary
}

/** Explicit merged view — see file docstring for why this merges rather
 * than replaces. Built as named fields (not `{ ...initial, ...detail }`)
 * so every field's type stays concrete instead of collapsing to
 * `unknown` when TS infers a spread-of-a-union's shape. */
interface MergedJobView {
  name: string
  status: string
  displayStatus: string
  docCountTotal: number
  docCountProcessed: number
  docCountFailed: number
  progressPct: number
  errorMessage: string | null
}

function mergeJobView(initial: IngestionJobSummary, detail: IngestionJobDetail | undefined): MergedJobView {
  if (!detail) {
    return {
      name: initial.name,
      status: initial.status,
      displayStatus: initial.status,
      docCountTotal: initial.docCountTotal,
      docCountProcessed: initial.docCountProcessed,
      docCountFailed: initial.docCountFailed,
      progressPct: initial.progressPct,
      errorMessage: null,
    }
  }
  return {
    name: initial.name, // detail never carries a name — see file docstring
    status: detail.status,
    displayStatus: detail.displayStatus,
    docCountTotal: detail.docCountTotal,
    docCountProcessed: detail.docCountProcessed,
    docCountFailed: detail.docCountFailed,
    progressPct: detail.progressPct,
    errorMessage: detail.errorMessage,
  }
}

export function JobProgressCard({ job: initial }: Props) {
  const { data: detail } = useJobDetail(initial.jobId)
  const job = mergeJobView(initial, detail)
  const phase = Math.min(Math.floor(job.progressPct / 25), 3)

  return (
    <div className="job-card">
      <div className="job-card-header">
        <span className="job-card-name">{job.name}</span>
        <StatusBadge status={job.displayStatus} />
      </div>

      <div className="progress-track">
        <div
          className="progress-fill"
          style={{ width: `${Math.min(job.progressPct, 100)}%` }}
          data-status={job.status}
        />
      </div>

      <div className="job-card-phases">
        {PHASES.map((p, i) => (
          <span key={p} className={i <= phase ? 'phase phase-done' : 'phase'}>
            {p}
          </span>
        ))}
      </div>

      <div className="job-card-stats mono">
        <span>
          {job.docCountProcessed.toLocaleString()} / {job.docCountTotal.toLocaleString()} docs
        </span>
        <span>{job.progressPct.toFixed(1)}%</span>
        {job.docCountFailed > 0 && <span className="job-card-fail">{job.docCountFailed} failed</span>}
      </div>

      {job.errorMessage && <p className="job-card-error">{job.errorMessage}</p>}
    </div>
  )
}
