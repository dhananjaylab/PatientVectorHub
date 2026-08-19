/**
 * dashboard/src/pages/admin/AdminUsersPage.tsx
 * New in Phase 9. Read-only per schemas/admin.py's UserListResponse —
 * there is no invite/deactivate endpoint in this API yet (doc 03's
 * "Invite, assign roles, deactivate" User Mgmt description is aspirational
 * beyond what routers/admin.py currently implements: GET /users only).
 */
import { ExactRoleGuard } from '../../components/common/RoleGuard'
import { StatusBadge } from '../../components/common/StatusBadge'
import { useAdminUsers } from '../../hooks/useAdmin'
import { getApiErrorMessage } from '../../lib/api'
import { roleLabel } from '../../lib/rbac'

function UsersTable() {
  const { data: users, isLoading, isError, error } = useAdminUsers()

  if (isLoading) return <p className="loading-text">Loading users…</p>
  if (isError) return <p className="field-error">{getApiErrorMessage(error)}</p>
  if (!users || users.length === 0) return <p className="empty-state">No users found for this tenant.</p>

  return (
    <table className="admin-table">
      <thead>
        <tr>
          <th>Email</th>
          <th>Role</th>
          <th>Status</th>
          <th>Last login</th>
          <th>Created</th>
        </tr>
      </thead>
      <tbody>
        {users.map((u) => (
          <tr key={u.id}>
            <td>{u.email}</td>
            <td>{roleLabel(u.role)}</td>
            <td>
              <StatusBadge status={u.is_active ? 'active' : 'revoked'} label={u.is_active ? 'active' : 'inactive'} />
            </td>
            <td className="mono">{u.last_login ? new Date(u.last_login).toLocaleString() : 'never'}</td>
            <td className="mono">{new Date(u.created_at).toLocaleDateString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function AdminUsersPage() {
  return (
    <ExactRoleGuard allow={['admin']}>
      <UsersTable />
    </ExactRoleGuard>
  )
}
