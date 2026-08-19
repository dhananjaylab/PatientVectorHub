import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * dashboard/src/pages/QueryPage.tsx
 * New in Phase 9. Thin page wrapper around QueryForm.
 */
import { QueryForm } from '../components/query/QueryForm';
export function QueryPage() {
    return (_jsxs("div", { className: "query-page-wrapper", children: [_jsx("h1", { children: "RAG Query" }), _jsx(QueryForm, {})] }));
}
