import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * dashboard/src/pages/IngestionPage.tsx
 * New in Phase 9. Job cards poll live detail via JobProgressCard itself.
 */
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useIngestionJobs } from '../hooks/useIngestionJobs';
import { JobProgressCard } from '../components/ingestion/JobProgressCard';
import { Pagination } from '../components/common/Pagination';
import { getApiErrorMessage } from '../lib/api';
const STATUS_FILTERS = ['', 'queued', 'running', 'completed', 'failed', 'cancelled'];
const PAGE_SIZE = 12;
export function IngestionPage() {
    const [status, setStatus] = useState('');
    const [offset, setOffset] = useState(0);
    const [searchParams] = useSearchParams();
    const highlightId = searchParams.get('highlight');
    const { data, isLoading, isError, error } = useIngestionJobs({
        status: status || undefined,
        limit: PAGE_SIZE,
        offset,
    });
    return (_jsxs("div", { className: "ingestion-page", children: [_jsxs("div", { className: "page-header", children: [_jsx("h1", { children: "Ingestion Jobs" }), _jsx(Link, { to: "/ingestion/new", className: "btn-primary", children: "New Batch Job" })] }), _jsx("div", { className: "status-filter-row", children: STATUS_FILTERS.map((s) => (_jsx("button", { type: "button", className: status === s ? 'tab-btn active' : 'tab-btn', onClick: () => {
                        setStatus(s);
                        setOffset(0);
                    }, children: s || 'All' }, s || 'all'))) }), isLoading && _jsx("p", { className: "loading-text", children: "Loading jobs\u2026" }), isError && _jsx("p", { className: "field-error", children: getApiErrorMessage(error) }), data && data.jobs.length === 0 && (_jsxs("div", { className: "empty-state", children: [_jsx("p", { children: "No ingestion jobs yet." }), _jsx(Link, { to: "/ingestion/new", className: "btn-ghost", children: "Start your first ingestion pipeline \u2192" })] })), _jsx("div", { className: "job-card-grid", children: data?.jobs.map((job) => (_jsx("div", { className: job.jobId === highlightId ? 'job-card-highlight' : undefined, children: _jsx(JobProgressCard, { job: job }) }, job.jobId))) }), data && _jsx(Pagination, { total: data.total, limit: data.limit, offset: data.offset, onOffsetChange: setOffset })] }));
}
