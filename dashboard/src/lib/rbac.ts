/**
 * dashboard/src/lib/rbac.ts
 *
 * Phase 9. Extracted from App.tsx's inline ROLE_LEVEL map so every page
 * that needs a role check (route guards, and now also per-element checks
 * like "only show the Export button to admin/auditor") shares one
 * definition instead of each place re-declaring its own copy that could
 * drift.
 *
 * Values match api-gateway/src/middleware/rbac.py's `_HIERARCHY` and
 * middleware/auth.py's `_ROLE_PRIORITY` exactly. This is a UX
 * convenience only — every one of these checks is re-enforced server-
 * side by require_role()/require_min_role() on the actual route; a
 * client-side bypass of this file gets a 403 from the API, not real
 * unauthorized access. See doc 05's Role table for what each role can
 * actually do.
 */
export type Role = 'admin' | 'engineer' | 'analyst' | 'auditor' | 'readonly'

export const ROLE_HIERARCHY: Record<Role, number> = {
  admin: 4,
  engineer: 3,
  analyst: 2,
  auditor: 1,
  readonly: 0,
}

export const ROLE_PRIORITY: Role[] = ['admin', 'engineer', 'analyst', 'auditor', 'readonly']

export function hasMinRole(role: string, min: Role): boolean {
  const level = ROLE_HIERARCHY[role as Role] ?? -1
  return level >= ROLE_HIERARCHY[min]
}

export function hasExactRole(role: string, ...allowed: Role[]): boolean {
  return (allowed as string[]).includes(role)
}

/** Human-readable label for role pills in the top bar / admin tables. */
export function roleLabel(role: string): string {
  const known = ROLE_PRIORITY as string[]
  if (!known.includes(role)) return 'Unknown'
  return role.charAt(0).toUpperCase() + role.slice(1)
}
