import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * dashboard/src/components/query/QueryForm.tsx
 *
 * New in Phase 9. Provider selector defaults to "Default" (omits
 * llm_provider from the request entirely) rather than pre-selecting
 * "anthropic" — see hooks/useRAGQuery.ts's docstring for why hardcoding
 * a default here would risk drifting from rag-engine's own
 * LLM_DEFAULT_PROVIDER setting. Document-type filter checkboxes are the
 * only filter offered — date_range/cohort_filter aren't in the real
 * QueryFilters schema yet (ADR-014 §3).
 */
import { useState } from 'react';
import { DOCUMENT_TYPES } from '../../hooks/useIngestionJobs';
import { useRAGQuery } from '../../hooks/useRAGQuery';
import { getApiErrorMessage } from '../../lib/api';
import { QueryResultCard } from './QueryResultCard';
const PROVIDERS = [
    { value: '', label: 'Default (server-configured)' },
    { value: 'anthropic', label: 'Anthropic Claude' },
    { value: 'openai', label: 'OpenAI GPT' },
    { value: 'gemini', label: 'Google Gemini' },
];
export function QueryForm() {
    const { mutate, isPending, data, isError, error } = useRAGQuery();
    const [text, setText] = useState('');
    const [topK, setTopK] = useState(10);
    const [provider, setProvider] = useState('');
    const [docTypes, setDocTypes] = useState(new Set());
    function toggleDocType(t) {
        setDocTypes((prev) => {
            const next = new Set(prev);
            if (next.has(t)) {
                next.delete(t);
            }
            else {
                next.add(t);
            }
            return next;
        });
    }
    function onSubmit(e) {
        e.preventDefault();
        if (text.trim().length < 3)
            return;
        mutate({
            query_text: text.trim(),
            top_k: topK,
            llm_provider: provider || undefined,
            filters: docTypes.size > 0 ? { document_types: Array.from(docTypes) } : undefined,
        });
    }
    return (_jsxs("div", { className: "query-page", children: [_jsxs("form", { onSubmit: onSubmit, className: "query-form", children: [_jsx("textarea", { value: text, onChange: (e) => setText(e.target.value), placeholder: "Clinical query \u2014 e.g. patients with type 2 diabetes and recent elevated HbA1c", rows: 4, minLength: 3, maxLength: 2000 }), _jsx("div", { className: "query-doc-type-filters", children: DOCUMENT_TYPES.map((t) => (_jsxs("label", { className: "chip-checkbox", children: [_jsx("input", { type: "checkbox", checked: docTypes.has(t), onChange: () => toggleDocType(t) }), t.replace(/_/g, ' ')] }, t))) }), _jsxs("div", { className: "query-controls", children: [_jsx("select", { value: provider, onChange: (e) => setProvider(e.target.value), children: PROVIDERS.map((p) => (_jsx("option", { value: p.value, children: p.label }, p.value))) }), _jsxs("label", { className: "top-k-field", children: ["top_k", _jsx("input", { type: "number", min: 1, max: 50, value: topK, onChange: (e) => setTopK(Number(e.target.value)) })] }), _jsx("button", { type: "submit", className: "btn-primary", disabled: isPending || text.trim().length < 3, children: isPending ? 'Querying…' : 'Run Query' })] })] }), isError && _jsx("p", { className: "field-error", children: getApiErrorMessage(error) }), data && (_jsxs("div", { className: "query-results", children: [_jsxs("div", { className: "query-answer", children: [_jsxs("div", { className: "query-answer-header", children: [_jsx("h3", { children: "Answer" }), _jsxs("span", { className: "mono query-latency", children: [data.latency_ms, "ms"] })] }), _jsx("p", { children: data.answer }), data.citations.length > 0 && (_jsxs("p", { className: "query-citations mono", children: ["Sources: ", data.citations.map((c) => `[${c.index}] ${c.document_type}`).join('  ')] }))] }), _jsx("div", { className: "query-result-list", children: data.results.map((r, i) => (_jsx(QueryResultCard, { result: r, citationIndex: data.citations.find((c) => c.doc_id === r.doc_id)?.index }, `${r.doc_id}-${i}`))) })] }))] }));
}
