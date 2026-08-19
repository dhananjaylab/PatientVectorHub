import { jsx as _jsx } from "react/jsx-runtime";
/**
 * dashboard/src/components/__tests__/JobProgressCard.test.tsx
 *
 * The second test here is the specific regression this component was
 * built to avoid — see JobProgressCard.tsx's docstring. Written before
 * settling on the mergeJobView() approach: an earlier version of this
 * component (`data ?? initial`, mirroring the original doc 35 sketch)
 * passed the first assertion but failed the second, rendering an empty
 * job-card-name once useJobDetail's first poll resolved.
 */
import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../../test/testUtils';
import { api } from '../../lib/api';
import { JobProgressCard } from '../ingestion/JobProgressCard';
vi.mock('../../lib/api', () => ({
    api: { get: vi.fn(), post: vi.fn() },
}));
const listSnapshot = {
    jobId: 'job-1',
    name: 'nightly-clinical-notes',
    status: 'running',
    docCountTotal: 100,
    docCountProcessed: 10,
    docCountFailed: 0,
    progressPct: 10,
    createdAt: '2026-08-01T00:00:00Z',
};
describe('JobProgressCard', () => {
    it('renders the list snapshot immediately, before any detail poll resolves', () => {
        vi.mocked(api.get).mockReturnValue(new Promise(() => { })); // never resolves
        renderWithProviders(_jsx(JobProgressCard, { job: listSnapshot }));
        expect(screen.getByText('nightly-clinical-notes')).toBeInTheDocument();
        expect(screen.getByText(/10 \/ 100 docs/)).toBeInTheDocument();
    });
    it('keeps showing the job name after the first detail poll resolves, even though detail has no name field', async () => {
        // GET /v1/ingest/jobs/{id} — routers/ingest.py's _to_response() has
        // no `name` key at all (see hooks/useIngestionJobs.ts docstring).
        vi.mocked(api.get).mockResolvedValue({
            data: {
                job_id: 'job-1',
                status: 'running',
                doc_count_total: 100,
                doc_count_processed: 55,
                doc_count_failed: 0,
                progress_pct: 55.0,
                error_message: null,
                created_at: '2026-08-01T00:00:00Z',
                display_status: 'running',
            },
        });
        renderWithProviders(_jsx(JobProgressCard, { job: listSnapshot }));
        // Wait for the poll to land (progress moves from the list snapshot's
        // 10% to detail's live 55%) — this is the signal that `detail` has
        // replaced/merged into what's rendered.
        await waitFor(() => expect(screen.getByText(/55 \/ 100 docs/)).toBeInTheDocument());
        // The regression: name must still be there. It never appears in any
        // detail response, so if it's showing now, it can only have survived
        // from the `initial` list snapshot via the merge.
        expect(screen.getByText('nightly-clinical-notes')).toBeInTheDocument();
    });
    it('shows the error message once a poll reports a failed job', async () => {
        vi.mocked(api.get).mockResolvedValue({
            data: {
                job_id: 'job-1',
                status: 'failed',
                doc_count_total: 100,
                doc_count_processed: 40,
                doc_count_failed: 3,
                progress_pct: 40.0,
                error_message: 'S3 access denied: raw/tenant-a/doc-88.pdf',
                created_at: '2026-08-01T00:00:00Z',
                display_status: 'failed',
            },
        });
        renderWithProviders(_jsx(JobProgressCard, { job: listSnapshot }));
        await waitFor(() => expect(screen.getByText(/S3 access denied/)).toBeInTheDocument());
        expect(screen.getByText('3 failed')).toBeInTheDocument();
    });
});
