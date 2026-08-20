import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * dashboard/src/pages/admin/AdminApiKeysPage.tsx
 *
 * New in Phase 9. `key_plaintext` is shown exactly once, in a modal the
 * person must explicitly dismiss — see hooks/useAdmin.ts's
 * CreateApiKeyResponse docstring: db/crud.py only ever persists the
 * SHA-256 hash, so this value is genuinely unrecoverable after this
 * render. There is no "show key again" affordance anywhere else in this
 * UI because there is no API call that could serve it.
 */
import { useState } from 'react';
import { ExactRoleGuard } from '../../components/common/RoleGuard';
import { StatusBadge } from '../../components/common/StatusBadge';
import { API_KEY_SCOPES, useApiKeys, useCreateApiKey, useRevokeApiKey, } from '../../hooks/useAdmin';
import { getApiErrorMessage } from '../../lib/api';
function CreateKeyForm({ onCreated }) {
    const createKey = useCreateApiKey();
    const [name, setName] = useState('');
    const [scopes, setScopes] = useState(new Set());
    const [expiresDays, setExpiresDays] = useState(90);
    function toggleScope(s) {
        setScopes((prev) => {
            const next = new Set(prev);
            if (next.has(s)) {
                next.delete(s);
            }
            else {
                next.add(s);
            }
            return next;
        });
    }
    async function onSubmit(e) {
        e.preventDefault();
        if (!name.trim() || scopes.size === 0)
            return;
        const result = await createKey.mutateAsync({ name: name.trim(), scopes: Array.from(scopes), expires_days: expiresDays });
        onCreated(result);
        setName('');
        setScopes(new Set());
    }
    return (_jsxs("form", { className: "create-key-form", onSubmit: onSubmit, children: [_jsx("input", { placeholder: "Key name", value: name, onChange: (e) => setName(e.target.value), maxLength: 100 }), _jsx("div", { className: "scope-checkboxes", children: API_KEY_SCOPES.map((s) => (_jsxs("label", { className: "chip-checkbox", children: [_jsx("input", { type: "checkbox", checked: scopes.has(s), onChange: () => toggleScope(s) }), s] }, s))) }), _jsxs("label", { className: "top-k-field", children: ["Expires (days)", _jsx("input", { type: "number", min: 1, max: 365, value: expiresDays, onChange: (e) => setExpiresDays(Number(e.target.value)) })] }), _jsx("button", { type: "submit", className: "btn-primary", disabled: !name.trim() || scopes.size === 0 || createKey.isPending, children: createKey.isPending ? 'Creating…' : 'Create API key' }), createKey.isError && _jsx("p", { className: "field-error", children: getApiErrorMessage(createKey.error) })] }));
}
function RevealModal({ result, onClose }) {
    return (_jsx("div", { className: "modal-backdrop", role: "dialog", "aria-modal": "true", children: _jsxs("div", { className: "modal", children: [_jsx("h2", { children: "API key created" }), _jsx("p", { className: "modal-warning", children: "This is shown once. Copy it now \u2014 it cannot be retrieved again." }), _jsx("code", { className: "mono key-reveal", children: result.key_plaintext }), _jsx("button", { type: "button", className: "btn-primary", onClick: onClose, children: "I've copied it \u2014 close" })] }) }));
}
function KeysTable() {
    const { data: keys, isLoading, isError, error } = useApiKeys();
    const revoke = useRevokeApiKey();
    if (isLoading)
        return _jsx("p", { className: "loading-text", children: "Loading keys\u2026" });
    if (isError)
        return _jsx("p", { className: "field-error", children: getApiErrorMessage(error) });
    if (!keys || keys.length === 0)
        return _jsx("p", { className: "empty-state", children: "No API keys yet." });
    return (_jsxs("table", { className: "admin-table", children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Name" }), _jsx("th", { children: "Scopes" }), _jsx("th", { children: "Status" }), _jsx("th", { children: "Expires" }), _jsx("th", { children: "Last used" }), _jsx("th", {})] }) }), _jsx("tbody", { children: keys.map((k) => (_jsxs("tr", { children: [_jsx("td", { children: k.name }), _jsx("td", { className: "mono", children: k.scopes.join(', ') }), _jsx("td", { children: _jsx(StatusBadge, { status: k.is_revoked ? 'revoked' : 'active' }) }), _jsx("td", { className: "mono", children: new Date(k.expires_at).toLocaleDateString() }), _jsx("td", { className: "mono", children: k.last_used_at ? new Date(k.last_used_at).toLocaleString() : 'never' }), _jsx("td", { children: !k.is_revoked && (_jsx("button", { type: "button", className: "btn-ghost", disabled: revoke.isPending, onClick: () => revoke.mutate(k.id), children: "Revoke" })) })] }, k.id))) })] }));
}
export function AdminApiKeysPage() {
    const [revealed, setRevealed] = useState(null);
    return (_jsx(ExactRoleGuard, { allow: ['admin'], children: _jsxs("div", { className: "admin-api-keys-page", children: [_jsx(CreateKeyForm, { onCreated: setRevealed }), _jsx(KeysTable, {}), revealed && _jsx(RevealModal, { result: revealed, onClose: () => setRevealed(null) })] }) }));
}
