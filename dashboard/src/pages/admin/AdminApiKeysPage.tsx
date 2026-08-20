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
import { useState, type FormEvent } from 'react'
import { ExactRoleGuard } from '../../components/common/RoleGuard'
import { StatusBadge } from '../../components/common/StatusBadge'
import {
  API_KEY_SCOPES,
  useApiKeys,
  useCreateApiKey,
  useRevokeApiKey,
  type ApiKeyScope,
  type CreateApiKeyResponse,
} from '../../hooks/useAdmin'
import { getApiErrorMessage } from '../../lib/api'

function CreateKeyForm({ onCreated }: { onCreated: (r: CreateApiKeyResponse) => void }) {
  const createKey = useCreateApiKey()
  const [name, setName] = useState('')
  const [scopes, setScopes] = useState<Set<ApiKeyScope>>(new Set())
  const [expiresDays, setExpiresDays] = useState(90)

  function toggleScope(s: ApiKeyScope) {
    setScopes((prev) => {
      const next = new Set(prev)
      if (next.has(s)) {
        next.delete(s)
      } else {
        next.add(s)
      }
      return next
    })
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!name.trim() || scopes.size === 0) return
    const result = await createKey.mutateAsync({ name: name.trim(), scopes: Array.from(scopes), expires_days: expiresDays })
    onCreated(result)
    setName('')
    setScopes(new Set())
  }

  return (
    <form className="create-key-form" onSubmit={onSubmit}>
      <input placeholder="Key name" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} />
      <div className="scope-checkboxes">
        {API_KEY_SCOPES.map((s) => (
          <label key={s} className="chip-checkbox">
            <input type="checkbox" checked={scopes.has(s)} onChange={() => toggleScope(s)} />
            {s}
          </label>
        ))}
      </div>
      <label className="top-k-field">
        Expires (days)
        <input type="number" min={1} max={365} value={expiresDays} onChange={(e) => setExpiresDays(Number(e.target.value))} />
      </label>
      <button type="submit" className="btn-primary" disabled={!name.trim() || scopes.size === 0 || createKey.isPending}>
        {createKey.isPending ? 'Creating…' : 'Create API key'}
      </button>
      {createKey.isError && <p className="field-error">{getApiErrorMessage(createKey.error)}</p>}
    </form>
  )
}

function RevealModal({ result, onClose }: { result: CreateApiKeyResponse; onClose: () => void }) {
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="modal">
        <h2>API key created</h2>
        <p className="modal-warning">This is shown once. Copy it now — it cannot be retrieved again.</p>
        <code className="mono key-reveal">{result.key_plaintext}</code>
        <button type="button" className="btn-primary" onClick={onClose}>
          I've copied it — close
        </button>
      </div>
    </div>
  )
}

function KeysTable() {
  const { data: keys, isLoading, isError, error } = useApiKeys()
  const revoke = useRevokeApiKey()

  if (isLoading) return <p className="loading-text">Loading keys…</p>
  if (isError) return <p className="field-error">{getApiErrorMessage(error)}</p>
  if (!keys || keys.length === 0) return <p className="empty-state">No API keys yet.</p>

  return (
    <table className="admin-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Scopes</th>
          <th>Status</th>
          <th>Expires</th>
          <th>Last used</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {keys.map((k) => (
          <tr key={k.id}>
            <td>{k.name}</td>
            <td className="mono">{k.scopes.join(', ')}</td>
            <td>
              <StatusBadge status={k.is_revoked ? 'revoked' : 'active'} />
            </td>
            <td className="mono">{new Date(k.expires_at).toLocaleDateString()}</td>
            <td className="mono">{k.last_used_at ? new Date(k.last_used_at).toLocaleString() : 'never'}</td>
            <td>
              {!k.is_revoked && (
                <button type="button" className="btn-ghost" disabled={revoke.isPending} onClick={() => revoke.mutate(k.id)}>
                  Revoke
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function AdminApiKeysPage() {
  const [revealed, setRevealed] = useState<CreateApiKeyResponse | null>(null)
  return (
    <ExactRoleGuard allow={['admin']}>
      <div className="admin-api-keys-page">
        <CreateKeyForm onCreated={setRevealed} />
        <KeysTable />
        {revealed && <RevealModal result={revealed} onClose={() => setRevealed(null)} />}
      </div>
    </ExactRoleGuard>
  )
}
