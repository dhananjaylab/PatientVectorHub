/**
 * dashboard/src/pages/QueryPage.tsx
 * New in Phase 9. Thin page wrapper around QueryForm.
 */
import { QueryForm } from '../components/query/QueryForm'

export function QueryPage() {
  return (
    <div className="query-page-wrapper">
      <h1>RAG Query</h1>
      <QueryForm />
    </div>
  )
}
