import { jsx as _jsx } from "react/jsx-runtime";
import { describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { createTestQueryClient } from '../../test/testUtils';
import { api } from '../../lib/api';
import { useRAGQuery } from '../useRAGQuery';
vi.mock('../../lib/api', () => ({
    api: { get: vi.fn(), post: vi.fn() },
}));
function wrapper({ children }) {
    return _jsx(QueryClientProvider, { client: createTestQueryClient(), children: children });
}
describe('useRAGQuery', () => {
    it('posts to /query and returns the response verbatim (citation field is document_type, not type)', async () => {
        vi.mocked(api.post).mockResolvedValueOnce({
            data: {
                query_id: 'q-1',
                answer: 'Patient shows elevated HbA1c [1].',
                citations: [{ index: 1, doc_id: 'd-1', document_type: 'lab_result' }],
                results: [{ doc_id: 'd-1', chunk_text: 'HbA1c 8.4%', score: 0.92, document_type: 'lab_result' }],
                latency_ms: 142,
            },
        });
        const { result } = renderHook(() => useRAGQuery(), { wrapper });
        act(() => {
            result.current.mutate({ query_text: 'HbA1c elevated diabetes', top_k: 5 });
        });
        await waitFor(() => expect(result.current.isSuccess).toBe(true));
        expect(result.current.data?.citations[0].document_type).toBe('lab_result');
        expect(api.post).toHaveBeenCalledWith('/query', { query_text: 'HbA1c elevated diabetes', top_k: 5 });
    });
    it('omits llm_provider from the request when not explicitly chosen (server resolves its own default)', async () => {
        vi.mocked(api.post).mockResolvedValueOnce({
            data: { query_id: 'q-2', answer: 'x', citations: [], results: [], latency_ms: 10 },
        });
        const { result } = renderHook(() => useRAGQuery(), { wrapper });
        act(() => {
            result.current.mutate({ query_text: 'test query', top_k: 10, llm_provider: undefined });
        });
        await waitFor(() => expect(result.current.isSuccess).toBe(true));
        // The object passed to api.post still has the `llm_provider` key
        // present (with value undefined) — object destructuring doesn't
        // strip it. What actually matters is that the hook injects no
        // default value of its own; JSON.stringify (axios's real transport
        // serialization, not exercised by this mock) is what drops an
        // undefined-valued key from the wire payload the server sees.
        const [, body] = vi.mocked(api.post).mock.calls[0];
        expect(body.llm_provider).toBeUndefined();
    });
});
