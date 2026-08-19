/**
 * dashboard/src/pages/NewJobPage.tsx
 * New in Phase 9. Thin page wrapper around NewJobForm.
 */
import { Link } from 'react-router'
import { NewJobForm } from '../components/ingestion/NewJobForm'

export function NewJobPage() {
  return (
    <div className="new-job-page">
      <div className="page-header">
        <h1>New Batch Job</h1>
        <Link to="/ingestion" className="btn-ghost">
          ← Back to jobs
        </Link>
      </div>
      <NewJobForm />
    </div>
  )
}
