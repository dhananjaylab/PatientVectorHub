import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { Link } from 'react-router';
export function NotFoundPage() {
    return (_jsxs("div", { className: "not-found-page", children: [_jsx("h1", { children: "404 \u2014 Not Found" }), _jsx(Link, { to: "/dashboard", className: "btn-ghost", children: "\u2190 Back to Dashboard" })] }));
}
