import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <div className="not-found-page">
      <h1>404 — Not Found</h1>
      <Link to="/dashboard" className="btn-ghost">
        ← Back to Dashboard
      </Link>
    </div>
  )
}
