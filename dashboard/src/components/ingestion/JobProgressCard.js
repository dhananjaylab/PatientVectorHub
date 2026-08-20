import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
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
import { useJobDetail } from '../../hooks/useIngestionJobs';
import { StatusBadge } from '../common/StatusBadge';
const PHASES = ['Reading', 'Chunking', 'Embedding', 'Storing'];
function mergeJobView(initial, detail) {
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
        };
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
    };
}
export function JobProgressCard({ job: initial }) {
    const { data: detail } = useJobDetail(initial.jobId);
    const job = mergeJobView(initial, detail);
    const phase = Math.min(Math.floor(job.progressPct / 25), 3);
    return (_jsxs("div", { className: "job-card", children: [_jsxs("div", { className: "job-card-header", children: [_jsx("span", { className: "job-card-name", children: job.name }), _jsx(StatusBadge, { status: job.displayStatus })] }), _jsx("div", { className: "progress-track", children: _jsx("div", { className: "progress-fill", style: { width: `${Math.min(job.progressPct, 100)}%` }, "data-status": job.status }) }), _jsx("div", { className: "job-card-phases", children: PHASES.map((p, i) => (_jsx("span", { className: i <= phase ? 'phase phase-done' : 'phase', children: p }, p))) }), _jsxs("div", { className: "job-card-stats mono", children: [_jsxs("span", { children: [job.docCountProcessed.toLocaleString(), " / ", job.docCountTotal.toLocaleString(), " docs"] }), _jsxs("span", { children: [job.progressPct.toFixed(1), "%"] }), job.docCountFailed > 0 && _jsxs("span", { className: "job-card-fail", children: [job.docCountFailed, " failed"] })] }), job.errorMessage && _jsx("p", { className: "job-card-error", children: job.errorMessage })] }));
}
