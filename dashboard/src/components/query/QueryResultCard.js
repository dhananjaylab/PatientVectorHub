import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
export function QueryResultCard({ result, citationIndex }) {
    const scorePct = Math.round(Math.max(0, Math.min(1, result.score)) * 100);
    return (_jsxs("div", { className: "query-result-card", children: [_jsx("div", { className: "query-result-score", style: { width: `${scorePct}%` } }), _jsxs("div", { className: "query-result-body", children: [_jsxs("div", { className: "query-result-header", children: [citationIndex != null && _jsxs("span", { className: "citation-badge", children: ["[", citationIndex, "]"] }), _jsx("span", { className: "doc-type-badge", children: result.document_type.replace(/_/g, ' ') }), _jsxs("span", { className: "query-result-score-label mono", children: [scorePct, "% match"] })] }), _jsx("p", { className: "query-result-text", children: result.chunk_text }), _jsx("p", { className: "query-result-doc-id mono", children: result.doc_id })] })] }));
}
