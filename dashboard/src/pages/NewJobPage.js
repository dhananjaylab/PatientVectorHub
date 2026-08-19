import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * dashboard/src/pages/NewJobPage.tsx
 * New in Phase 9. Thin page wrapper around NewJobForm.
 */
import { Link } from 'react-router';
import { NewJobForm } from '../components/ingestion/NewJobForm';
export function NewJobPage() {
    return (_jsxs("div", { className: "new-job-page", children: [_jsxs("div", { className: "page-header", children: [_jsx("h1", { children: "New Batch Job" }), _jsx(Link, { to: "/ingestion", className: "btn-ghost", children: "\u2190 Back to jobs" })] }), _jsx(NewJobForm, {})] }));
}
