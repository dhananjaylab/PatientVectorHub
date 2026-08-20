import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
export function Pagination({ total, limit, offset, onOffsetChange }) {
    const page = Math.floor(offset / limit) + 1;
    const pageCount = Math.max(1, Math.ceil(total / limit));
    const hasPrev = offset > 0;
    const hasNext = offset + limit < total;
    if (total <= limit && offset === 0)
        return null;
    return (_jsxs("div", { className: "pagination", children: [_jsx("button", { type: "button", disabled: !hasPrev, onClick: () => onOffsetChange(Math.max(0, offset - limit)), children: "\u2190 Prev" }), _jsxs("span", { children: ["Page ", page, " / ", pageCount, " \u00B7 ", total.toLocaleString(), " total"] }), _jsx("button", { type: "button", disabled: !hasNext, onClick: () => onOffsetChange(offset + limit), children: "Next \u2192" })] }));
}
