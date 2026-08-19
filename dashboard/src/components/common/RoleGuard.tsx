/**
 * dashboard/src/components/common/RoleGuard.tsx
 *
 * Extracted from App.tsx's Phase 1 inline `Guard` component so admin
 * sub-pages (AdminApiKeysPage, AdminUsersPage — which need a stricter
 * admin-only check than the /admin/* route-level guard's engineer+
 * floor) can reuse the exact same 403 rendering instead of duplicating
 * it. Behavior is unchanged from the original: this is a UX convenience
 * only, every check here is re-enforced server-side.
 */
import type { ReactNode } from 'react'
import { useAuthStore } from '../../stores/useAuthStore'
import { hasMinRole, hasExactRole, type Role } from '../../lib/rbac'

interface MinRoleProps {
  children: ReactNode
  min: Role
}

export function RoleGuard({ children, min }: MinRoleProps) {
  const { role } = useAuthStore()
  if (!hasMinRole(role, min)) {
    return <div className="error-403">403 — role '{role}' cannot access this page.</div>
  }
  return children
}

interface ExactRoleProps {
  children: ReactNode
  allow: Role[]
}

export function ExactRoleGuard({ children, allow }: ExactRoleProps) {
  const { role } = useAuthStore()
  if (!hasExactRole(role, ...allow)) {
    return <div className="error-403">403 — role '{role}' cannot access this page.</div>
  }
  return children
}
